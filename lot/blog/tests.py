import tempfile
import time
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .forms import TOKEN_SALT
from .models import BlogSettings, Comment, MediaAsset, Post, PostAutosave, Tag
from .rendering import render_markdown

TEMP_MEDIA = tempfile.mkdtemp(prefix="lot-blog-test-media-")


def aged_token(post, seconds=10):
    return signing.dumps({"p": post.pk, "t": int(time.time()) - seconds}, salt=TOKEN_SALT)


def image_file(name="photo.jpg", size=(1200, 800), fmt="JPEG", exif=None):
    buf = BytesIO()
    kwargs = {"exif": exif} if exif else {}
    Image.new("RGB", size, "#2c570e").save(buf, fmt, **kwargs)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


class RenderingTests(TestCase):
    def test_markdown_basics_and_heading_demotion(self):
        html = render_markdown("# Big\n\n## Section\n\n**bold** and *it*\n\n> quoted\n\n- a\n- b")
        self.assertIn("<h2>Big</h2>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<blockquote>", html)
        self.assertIn("<li>a</li>", html)
        self.assertNotIn("<h1", html)

    def test_strips_scripts_handlers_and_js_links(self):
        html = render_markdown(
            '<script>alert(1)</script>\n\n<img src="x.jpg" onerror="alert(2)">\n\n'
            "[click](javascript:alert(3))\n\n<a href=\"javascript:alert(4)\">x</a>\n\n<iframe src=\"https://evil\"></iframe>"
        )
        for bad in ("<script", "onerror", "javascript:", "<iframe"):
            self.assertNotIn(bad, html)

    def test_single_image_becomes_captioned_figure(self):
        html = render_markdown("Intro\n\n![Sunset on PCH](/media/a.jpg)\n\nOutro")
        self.assertIn("<figure>", html)
        self.assertIn('alt="Sunset on PCH"', html)
        self.assertIn("<figcaption>Sunset on PCH</figcaption>", html)
        self.assertIn('loading="lazy"', html)

    def test_title_overrides_caption_and_empty_alt_has_none(self):
        html = render_markdown('![alt text](/a.jpg "The caption")')
        self.assertIn("<figcaption>The caption</figcaption>", html)
        self.assertNotIn("<figcaption>", render_markdown("![](/a.jpg)"))

    def test_consecutive_images_become_gallery(self):
        html = render_markdown("![One](/1.jpg)\n![Two](/2.jpg)\n![Three](/3.jpg)")
        self.assertIn('class="gallery cols-3"', html)
        self.assertEqual(html.count("<figure>"), 3)

    def test_unknown_classes_dropped(self):
        html = render_markdown('<div class="gallery evil-overlay">x</div>')
        self.assertIn('class="gallery"', html)
        self.assertNotIn("evil-overlay", html)

    def test_legacy_html_body_still_renders(self):
        html = render_markdown("<p>Hello</p>\n<h2>Part</h2>\n<ul><li>x</li></ul>")
        self.assertIn("<h2>Part</h2>", html)
        self.assertIn("<li>x</li>", html)


class BlogFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.staff = User.objects.create_superuser("owner", "owner@example.com", "pw-123-secure")
        cls.customer = User.objects.create_user("customer", "c@example.com", "pw-123-secure")
        cls.tag = Tag.objects.create(name="Suspension", slug="suspension")
        cls.live = Post.objects.create(
            title="Coilovers installed", body="Lowered it **today**.", status=Post.Status.PUBLISHED,
            published_at=now - timedelta(days=1), excerpt="Finally low.",
        )
        cls.live.tags.add(cls.tag)
        cls.draft = Post.objects.create(title="Secret draft about turbo", body="turbo plans", status=Post.Status.DRAFT)
        cls.scheduled = Post.objects.create(
            title="Scheduled turbo reveal", body="turbo soon", status=Post.Status.PUBLISHED,
            published_at=now + timedelta(days=3),
        )

    def setUp(self):
        cache.clear()


class VisibilityTests(BlogFixtureMixin, TestCase):
    def test_slug_generated_and_unique(self):
        self.assertEqual(self.live.slug, "coilovers-installed")
        twin = Post.objects.create(title="Coilovers installed")
        self.assertEqual(twin.slug, "coilovers-installed-2")

    def test_drafts_and_scheduled_posts_are_private(self):
        for post in (self.draft, self.scheduled):
            with self.subTest(post=post.title):
                self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 404)
        month = self.live.published_month
        pages = ["/blog/", "/blog/?q=turbo", f"/blog/{month.year}/{month.month}/", "/blog/feed/"]
        for url in pages:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertNotIn("Secret draft", html)
                self.assertNotIn("Scheduled turbo", html)
        self.assertContains(self.client.get("/blog/"), "Coilovers installed")

    def test_customers_cannot_see_drafts_even_logged_in(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)
        resp = self.client.get(reverse("admin:blog_post_preview", args=[self.draft.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("admin:login"), resp["Location"])

    def test_staff_can_preview_draft(self):
        self.client.force_login(self.staff)
        resp = self.client.get(reverse("admin:blog_post_preview", args=[self.draft.pk]))
        self.assertContains(resp, "Secret draft about turbo")
        self.assertContains(resp, "this is a draft")
        self.assertEqual(resp["X-Robots-Tag"], "noindex, nofollow")

    def test_tag_and_search_filters(self):
        self.assertContains(self.client.get("/blog/tag/suspension/"), "Coilovers installed")
        self.assertContains(self.client.get("/blog/?q=lowered"), "Coilovers installed")
        self.assertContains(self.client.get("/blog/?q=nothing-matches-this"), "Nothing matches")

    def test_month_archive(self):
        old = Post.objects.create(title="Bought the car", status=Post.Status.PUBLISHED,
                                  published_at=timezone.now() - timedelta(days=120))
        month, old_month = self.live.published_month, old.published_month
        home = self.client.get("/blog/").content.decode()
        self.assertIn(f"/blog/{month.year}/{month.month}/", home)
        self.assertIn(f"/blog/{old_month.year}/{old_month.month}/", home)
        self.assertIn(old_month.strftime("%B %Y"), home)

        resp = self.client.get(f"/blog/{old_month.year}/{old_month.month}/")
        self.assertContains(resp, "Bought the car")
        self.assertNotContains(resp, "Coilovers installed")
        self.assertContains(resp, f"/blog/{month.year}/{month.month}/")  # link to the newer month

        self.assertEqual(self.client.get("/blog/2026/13/").status_code, 404)
        self.assertEqual(self.client.get("/blog/1999/1/").status_code, 404)

    def test_pagination(self):
        BlogSettings.objects.update_or_create(pk=1, defaults={"posts_per_page": 3})
        for i in range(8):
            Post.objects.create(title=f"Entry {i}", status=Post.Status.PUBLISHED,
                                published_at=timezone.now() - timedelta(days=10 + i))
        page2 = self.client.get("/blog/?page=2")
        self.assertEqual(page2.status_code, 200)
        self.assertContains(page2, 'aria-current="page">2</span>')
        self.assertEqual(self.client.get("/blog/?page=99").status_code, 200)

    def test_public_pages_never_reveal_admin_url(self):
        admin_prefix = reverse("admin:index")
        for url in ["/", "/blog/", self.live.get_absolute_url(), "/contact/"]:
            with self.subTest(url=url):
                self.assertNotIn(admin_prefix, self.client.get(url).content.decode())

    def test_post_page_metadata(self):
        html = self.client.get(self.live.get_absolute_url()).content.decode()
        self.assertIn('property="og:type" content="article"', html)
        self.assertIn('rel="canonical"', html)
        self.assertIn("application/ld+json", html)
        self.assertIn("<strong>today</strong>", html)


class CommentTests(BlogFixtureMixin, TestCase):
    def comment(self, post=None, ip="10.0.0.1", token=None, **overrides):
        post = post or self.live
        data = {"name": "Kenji", "email": "Kenji@Example.com", "body": "Great build!", "website": "",
                "token": token if token is not None else aged_token(post)}
        data.update(overrides)
        return self.client.post(reverse("blog:comment", args=[post.slug]), data, REMOTE_ADDR=ip)

    def test_comment_held_for_approval_then_shown_without_email(self):
        resp = self.comment()
        self.assertRedirects(resp, f"{self.live.get_absolute_url()}#comments", fetch_redirect_response=False)
        c = Comment.objects.get()
        self.assertEqual(c.status, Comment.Status.PENDING)
        self.assertEqual(c.email, "kenji@example.com")
        self.assertTrue(c.ip_hash and "10.0.0.1" not in c.ip_hash)
        self.assertNotContains(self.client.get(self.live.get_absolute_url()), "Great build!")

        c.status = Comment.Status.APPROVED
        c.save()
        html = self.client.get(self.live.get_absolute_url()).content.decode()
        self.assertIn("Great build!", html)
        self.assertIn("Kenji", html)
        self.assertNotIn("kenji@example.com", html.lower())

    def test_success_message_shown(self):
        resp = self.comment()
        page = self.client.get(resp["Location"])
        self.assertContains(page, "will appear once it")

    def test_comment_html_is_escaped(self):
        self.comment(body='<script>alert("x")</script><b onclick=1>hi</b>', name="<img src=x onerror=alert(1)>")
        Comment.objects.update(status=Comment.Status.APPROVED)
        html = self.client.get(self.live.get_absolute_url()).content.decode()
        self.assertNotIn('<script>alert("x")', html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)

    def test_honeypot_silently_drops(self):
        resp = self.comment(website="http://spam.example")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Comment.objects.count(), 0)

    def test_too_fast_and_forged_tokens_rejected(self):
        resp = self.comment(token=aged_token(self.live, seconds=0))
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "That was quick", status_code=400)
        self.assertEqual(self.comment(token="forged").status_code, 400)
        self.assertEqual(self.comment(token=aged_token(self.draft)).status_code, 400)
        self.assertEqual(Comment.objects.count(), 0)

    def test_server_side_validation(self):
        resp = self.comment(email="not-an-email", body="")
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Please fix the highlighted fields", status_code=400)
        self.assertEqual(self.comment(body="x" * 3001).status_code, 400)
        self.assertEqual(Comment.objects.count(), 0)

    def test_rate_limit_and_duplicates(self):
        for i in range(3):
            self.assertEqual(self.comment(body=f"Comment number {i}").status_code, 302)
        resp = self.comment(body="One too many")
        self.assertContains(resp, "commenting a lot", status_code=400)
        self.assertEqual(self.comment(body="From elsewhere", ip="10.0.0.2").status_code, 302)
        resp = self.comment(body="From elsewhere", ip="10.0.0.3")
        self.assertContains(resp, "already posted", status_code=400)
        self.assertEqual(Comment.objects.count(), 4)

    def test_moderation_settings(self):
        cfg = BlogSettings.load()
        cfg.blocked_words = "casino"
        cfg.save()
        self.comment(body="Visit my CASINO")
        self.assertEqual(Comment.objects.get().status, Comment.Status.SPAM)

        Comment.objects.all().delete()
        Comment.objects.create(post=self.live, email="known@example.com", body="old", status=Comment.Status.APPROVED)
        self.comment(email="known@example.com", body="Back again", ip="10.0.0.9")
        self.assertEqual(Comment.objects.get(body="Back again").status, Comment.Status.APPROVED)

        cfg.require_approval = False
        cfg.save()
        self.comment(email="new@example.com", body="Instant", ip="10.0.0.10")
        self.assertEqual(Comment.objects.get(body="Instant").status, Comment.Status.APPROVED)
        self.comment(email="new2@example.com", body="see http://a.com http://b.com http://c.com", ip="10.0.0.11")
        self.assertEqual(Comment.objects.get(email="new2@example.com").status, Comment.Status.PENDING)

    def test_closed_comments_and_drafts(self):
        Post.objects.filter(pk=self.live.pk).update(allow_comments=False)
        self.assertNotContains(self.client.get(self.live.get_absolute_url()), 'id="comment-form"')
        self.comment()
        self.assertEqual(Comment.objects.count(), 0)
        self.assertEqual(self.comment(post=self.draft).status_code, 404)

    def test_admin_moderation_actions(self):
        c = Comment.objects.create(post=self.live, email="a@example.com", body="hello")
        self.client.force_login(self.staff)
        url = reverse("admin:blog_comment_changelist")
        self.assertRedirects(self.client.get(url), f"{url}?status__exact=pending")
        self.assertContains(self.client.get(f"{url}?status__exact=pending"), "a@example.com")
        self.client.post(url + "?status__exact=pending", {"action": "approve", "_selected_action": [c.pk]})
        c.refresh_from_db()
        self.assertEqual(c.status, Comment.Status.APPROVED)
        self.assertIsNotNone(c.moderated_at)
        self.client.post(url + "?status__exact=approved", {"action": "reject", "_selected_action": [c.pk]})
        c.refresh_from_db()
        self.assertEqual(c.status, Comment.Status.REJECTED)


def post_form(**overrides):
    data = {
        "title": "My new post", "slug": "", "excerpt": "", "body": "Hello **world**",
        "published_at_0": "", "published_at_1": "", "updated_on": "", "allow_comments": "on",
        "author": "", "cover_alt": "", "cover_caption": "", "meta_description": "", "schema_type": "BlogPosting",
        "_continue": "1",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class EditorTests(BlogFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_editor_pages_render(self):
        resp = self.client.get(reverse("admin:blog_post_add"))
        self.assertContains(resp, 'id="editor-config"')
        self.assertContains(resp, "Save draft")
        resp = self.client.get(reverse("admin:blog_post_change", args=[self.live.pk]))
        self.assertContains(resp, "Unpublish")
        self.assertContains(resp, "Update")

    def test_save_draft_then_publish_then_unpublish(self):
        resp = self.client.post(reverse("admin:blog_post_add"), post_form(_save="1"))
        post = Post.objects.get(title="My new post")
        self.assertRedirects(resp, reverse("admin:blog_post_change", args=[post.pk]), fetch_redirect_response=False)
        self.assertEqual(post.status, Post.Status.DRAFT)
        self.assertEqual(post.slug, "my-new-post")
        self.assertIsNone(post.published_at)
        self.assertEqual(post.author, self.staff)

        change = reverse("admin:blog_post_change", args=[post.pk])
        self.client.post(change, post_form(_publish="1", author=self.staff.pk, slug="my-new-post"))
        post.refresh_from_db()
        self.assertEqual(post.status, Post.Status.PUBLISHED)
        self.assertIsNotNone(post.published_at)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 200)

        self.client.post(change, post_form(_unpublish="1", author=self.staff.pk, slug="my-new-post"))
        post.refresh_from_db()
        self.assertEqual(post.status, Post.Status.DRAFT)
        self.client.logout()
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 404)

    def test_publish_with_future_date_schedules(self):
        future = timezone.localtime(timezone.now() + timedelta(days=2))
        self.client.post(reverse("admin:blog_post_add"), post_form(
            _publish="1", published_at_0=future.strftime("%Y-%m-%d"), published_at_1=future.strftime("%H:%M:%S")))
        post = Post.objects.get(title="My new post")
        self.assertTrue(post.is_scheduled)
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 404)

    def test_reserved_slug_rejected(self):
        resp = self.client.post(reverse("admin:blog_post_add"), post_form(slug="feed"))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Post.objects.filter(slug="feed").exists())

    def test_delete_with_confirmation(self):
        url = reverse("admin:blog_post_delete", args=[self.draft.pk])
        self.assertContains(self.client.get(url), "Are you sure")
        self.client.post(url, {"post": "yes"})
        self.assertFalse(Post.objects.filter(pk=self.draft.pk).exists())

    def test_unsaved_preview_does_not_save(self):
        count = Post.objects.count()
        resp = self.client.post(reverse("admin:blog_post_preview_new"), post_form(title="Preview only", body="## Hi"))
        self.assertContains(resp, "Preview only")
        self.assertContains(resp, "<h2>Hi</h2>")
        self.assertEqual(Post.objects.count(), count)

        resp = self.client.post(reverse("admin:blog_post_preview", args=[self.live.pk]),
                                post_form(title="Edited title", slug=self.live.slug))
        self.assertContains(resp, "Edited title")
        self.live.refresh_from_db()
        self.assertEqual(self.live.title, "Coilovers installed")

    def test_render_endpoint_sanitizes(self):
        resp = self.client.post(reverse("admin:blog_post_render"), {"body": "**x**<script>bad()</script>"})
        self.assertIn("<strong>x</strong>", resp.json()["html"])
        self.assertNotIn("<script", resp.json()["html"])

    def test_autosave_and_restore_offer(self):
        url = reverse("admin:blog_post_autosave")
        resp = self.client.post(url, {"post_id": self.live.pk, "title": "T", "excerpt": "", "body": "unsaved words"})
        self.assertTrue(resp.json()["ok"])
        self.assertEqual(PostAutosave.objects.get(post=self.live).body, "unsaved words")
        page = self.client.get(reverse("admin:blog_post_change", args=[self.live.pk]))
        self.assertContains(page, "unsaved words")

        self.client.post(url, {"post_id": self.live.pk, "discard": "1"})
        self.assertFalse(PostAutosave.objects.exists())

        self.client.post(url, {"title": "Brand new", "body": "draft text"})
        self.assertTrue(PostAutosave.objects.filter(post__isnull=True).exists())
        self.client.post(reverse("admin:blog_post_add"), post_form(_save="1"))
        self.assertFalse(PostAutosave.objects.exists(), "saving the post clears its autosave")

    def test_upload_optimizes_and_strips_metadata(self):
        exif = Image.Exif()
        exif[0x010F] = "SecretCam"
        exif[0x0112] = 6  # rotated: the saved image should come out upright (portrait)
        resp = self.client.post(reverse("admin:blog_post_upload"),
                                {"image": image_file(size=(3000, 2000), exif=exif.tobytes())})
        self.assertEqual(resp.status_code, 200, resp.content)
        asset = MediaAsset.objects.get()
        self.assertIn("/media/blog/", resp.json()["url"])
        with Image.open(asset.image.path) as saved:
            self.assertEqual(saved.size, (1333, 2000))
            self.assertNotIn(0x010F, saved.getexif())
        self.assertTrue(asset.thumb)
        self.assertNotIn("photo", asset.image.name)

    def test_upload_rejects_non_images(self):
        fake = SimpleUploadedFile("evil.jpg", b"<?php echo 1; ?>", content_type="image/jpeg")
        resp = self.client.post(reverse("admin:blog_post_upload"), {"image": fake})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(MediaAsset.objects.count(), 0)

    def test_cover_upload_creates_thumbnail(self):
        self.client.post(reverse("admin:blog_post_add"), post_form(cover_image=image_file(size=(3200, 1800))))
        post = Post.objects.get(title="My new post")
        self.assertEqual((post.cover_width, post.cover_height), (2400, 1350))
        self.assertTrue(post.cover_thumb)

    def test_editor_endpoints_require_staff(self):
        self.client.force_login(self.customer)
        for name in ["admin:blog_post_render", "admin:blog_post_autosave", "admin:blog_post_upload"]:
            with self.subTest(name=name):
                resp = self.client.post(reverse(name), {"body": "x"})
                self.assertEqual(resp.status_code, 302)
                self.assertIn(reverse("admin:login"), resp["Location"])
        self.assertFalse(PostAutosave.objects.exists())


class AdminSecurityTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_admin_lives_at_configured_path(self):
        self.assertEqual(reverse("admin:index"), "/" + settings.ADMIN_URL)
        if settings.ADMIN_URL != "admin/":
            self.assertEqual(self.client.get("/admin/").status_code, 404)

    def test_admin_login_is_throttled(self):
        url = reverse("admin:login")
        for _ in range(10):
            self.assertEqual(self.client.post(url, {"username": "x", "password": "wrong"}).status_code, 200)
        self.assertEqual(self.client.post(url, {"username": "x", "password": "wrong"}).status_code, 429)

    def test_customers_cannot_log_into_admin(self):
        User.objects.create_user("buyer", "b@example.com", "pw-123-secure")
        self.client.post(reverse("admin:login"), {"username": "buyer", "password": "pw-123-secure"})
        resp = self.client.get(reverse("admin:index"))
        self.assertEqual(resp.status_code, 302)
