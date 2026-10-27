import hashlib
import hmac
import json
import tempfile
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from blog.models import Post
from shop.models import Category, Order, OrderItem, Product, ShippingMethod, Variant

WEBHOOK_SECRET = "whsec_test_secret"


def signed(payload, secret=WEBHOOK_SECRET):
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class ShopTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Category.objects.create(name="Apparel", slug="apparel")
        cls.product = Product.objects.create(category=cat, name="Tee", slug="tee", price=Decimal("30.00"))
        cls.variant = Variant.objects.create(product=cls.product, name="M", stock=3)
        cls.sold_out = Product.objects.create(category=cat, name="Gone", slug="gone", price=Decimal("10.00"))
        Variant.objects.create(product=cls.sold_out, name="One", stock=0)
        cls.ship = ShippingMethod.objects.create(name="Standard", price=Decimal("6.00"))


class CartTests(ShopTestCase):
    def test_add_clamps_to_stock(self):
        self.client.post(reverse("shop:cart_add"), {"variant": self.variant.pk, "quantity": 10})
        self.assertEqual(self.client.session["cart"], {str(self.variant.pk): 3})

    def test_update_and_remove(self):
        self.client.post(reverse("shop:cart_add"), {"variant": self.variant.pk, "quantity": 1})
        self.client.post(reverse("shop:cart_update", args=[self.variant.pk]), {"quantity": 2})
        self.assertEqual(self.client.session["cart"][str(self.variant.pk)], 2)
        self.client.post(reverse("shop:cart_remove", args=[self.variant.pk]))
        self.assertEqual(self.client.session["cart"], {})

    def test_sold_out_hides_add_to_cart(self):
        html = self.client.get(self.sold_out.get_absolute_url()).content.decode()
        self.assertNotIn("Add to cart", html)
        self.assertIn("Sold out", html)
        self.assertIn("Add to cart", self.client.get(self.product.get_absolute_url()).content.decode())

    def test_cannot_add_sold_out_variant(self):
        v = self.sold_out.variants.get()
        self.client.post(reverse("shop:cart_add"), {"variant": v.pk, "quantity": 1})
        self.assertEqual(self.client.session.get("cart", {}), {})


CHECKOUT_DATA = {
    "email": "buyer@example.com",
    "full_name": "Test Buyer",
    "address_line1": "1 Main St",
    "city": "Austin",
    "region": "TX",
    "postal_code": "78701",
    "country": "US",
}


@override_settings(STRIPE_SECRET_KEY="sk_test_x", STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class CheckoutTests(ShopTestCase):
    def _checkout(self, **extra):
        self.client.post(reverse("shop:cart_add"), {"variant": self.variant.pk, "quantity": 2})
        fake = SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")
        with mock.patch("shop.views.stripe.checkout.Session.create", return_value=fake) as create:
            resp = self.client.post(reverse("shop:checkout"), {**CHECKOUT_DATA, "shipping_method": self.ship.pk, **extra})
        return resp, create

    def test_checkout_opt_in_subscribes(self):
        from core.models import Subscriber
        self._checkout()
        self.assertFalse(Subscriber.objects.exists())
        self._checkout(subscribe="on")
        self.assertEqual(Subscriber.objects.get().source, Subscriber.Source.CHECKOUT)

    def test_checkout_creates_order_and_redirects_to_stripe(self):
        resp, create = self._checkout()
        self.assertRedirects(resp, "https://checkout.stripe.com/c/pay/cs_test_123", fetch_redirect_response=False)
        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total, Decimal("66.00"))
        self.assertEqual(order.stripe_session_id, "cs_test_123")
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["line_items"][0]["price_data"]["unit_amount"], 3000)
        self.assertEqual(kwargs["metadata"]["order_id"], str(order.pk))
        self.assertIn("/checkout/success/?session_id={CHECKOUT_SESSION_ID}", kwargs["success_url"])
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 3, "stock must not change until the webhook confirms payment")

    def _webhook(self, order, event_type="checkout.session.completed", secret=WEBHOOK_SECRET):
        payload = json.dumps({
            "id": "evt_1",
            "type": event_type,
            "data": {"object": {
                "id": order.stripe_session_id,
                "payment_status": "paid",
                "payment_intent": "pi_123",
                "amount_total": 6600,
                "metadata": {"order_id": str(order.pk)},
            }},
        })
        return self.client.post(
            reverse("shop:stripe_webhook"), payload, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=signed(payload, secret),
        )

    def test_webhook_marks_paid_and_decrements_stock_once(self):
        self._checkout()
        order = Order.objects.get()
        self.assertEqual(self._webhook(order).status_code, 200)
        self.assertEqual(self._webhook(order).status_code, 200)  # Stripe retries must be harmless
        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.stripe_payment_intent, "pi_123")
        self.assertEqual(self.variant.stock, 1)

        resp = self.client.get(reverse("shop:checkout_success") + "?session_id=cs_test_123")
        self.assertContains(resp, "Payment confirmed")
        self.assertEqual(self.client.session["cart"], {})

    def test_webhook_rejects_bad_signature(self):
        self._checkout()
        order = Order.objects.get()
        self.assertEqual(self._webhook(order, secret="whsec_wrong").status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_expired_session_cancels_order(self):
        self._checkout()
        order = Order.objects.get()
        self._webhook(order, event_type="checkout.session.expired")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_stock_never_negative(self):
        order = Order.objects.create(email="a@b.c", full_name="A", address_line1="x", city="y",
                                     postal_code="1", shipping_name="S", total=Decimal("30"),
                                     stripe_session_id="cs_x")
        OrderItem.objects.create(order=order, variant=self.variant, product_name="Tee", variant_name="M",
                                 unit_price=Decimal("30"), quantity=5)
        payload_order = order
        self._webhook(payload_order)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 0)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="lot-test-media-"))
class PageSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command
        call_command("seed", verbosity=0)
        cls.admin = User.objects.create_superuser("boss", "boss@example.com", "pw-123-secure")

    def test_storefront_pages(self):
        post = Post.objects.first()
        product = Product.objects.first()
        urls = [
            "/", "/shop/", "/shop/apparel/", product.get_absolute_url(), "/cart/", "/faq/", "/contact/",
            "/blog/", "/blog/tag/culture/", "/blog/?q=coilovers", "/blog/feed/",
            post.get_absolute_url(),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/does-not-exist/").status_code, 404)
        for gone in ["/account/", "/account/login/", "/account/register/"]:
            self.assertEqual(self.client.get(gone).status_code, 404)
        self.assertRedirects(self.client.get("/journal/tag/culture/"), "/blog/tag/culture/", status_code=301)

    def test_post_has_schema_and_share_links(self):
        html = self.client.get(Post.objects.get(slug="night-meet-notes-clean-builds").get_absolute_url()).content.decode()
        self.assertIn('application/ld+json', html)
        self.assertIn('"@type": "BlogPosting"', html)
        self.assertIn("twitter.com/intent/tweet", html)
        self.assertNotIn("Shop the story", html)

    def test_blog_pages_only_link_to_the_store(self):
        for url in ["/", "/?page=2", "/blog/", "/contact/", Post.objects.published().first().get_absolute_url()]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertEqual(html.count('href="/shop/'), 2)  # desktop nav + mobile menu
                for store_bit in ['href="/cart/"', 'href="/faq/"', "Stripe"]:
                    self.assertNotIn(store_bit, html)
                self.assertIn("data-subscribe-popup", html)
                self.assertIn('action="/subscribe/"', html)
                self.assertIn("theme-dark", html)
        shop = self.client.get("/shop/").content.decode()
        self.assertNotIn("theme-dark", shop)
        for store_bit in ['href="/cart/"', 'href="/faq/"', "Payments secured by Stripe"]:
            self.assertIn(store_bit, shop)
        self.assertNotIn("data-subscribe-popup", shop)
        self.assertIn('href="/cart/"', self.client.get("/faq/").content.decode())

    def test_sections_and_home(self):
        names = list(Category.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Prints", "Apparel", "Car Accessories", "Accessories", "Stickers"])
        prints = Product.objects.filter(category__slug="prints")
        self.assertEqual(prints.count(), 3)
        sizes = [(v.name, str(v.price)) for v in prints.first().variants.all()]
        self.assertEqual(sizes, [("12 × 18 in.", "45.00"), ("18 × 24 in.", "75.00"), ("24 × 36 in.", "120.00")])
        shop = self.client.get("/shop/").content.decode()
        self.assertLess(shop.index('id="row-prints"'), shop.index('id="row-apparel"'))
        html = self.client.get("/").content.decode()
        self.assertIn('href="/shop/" class="nav-link">Store</a>', html)
        self.assertIn("Featured articles", html)
        self.assertIn("data-hero", html)
        self.assertNotIn("<video", html)  # no video uploaded: still image instead
        featured = Post.objects.published().filter(is_featured=True).first()
        first_article = html.index('<article class="group">')
        self.assertIn(featured.get_absolute_url(), html[first_article:first_article + 600])
        self.assertNotIn("Notes from the garage", html)

        from blog.models import PostCategory
        local = PostCategory.objects.get(name="Local")
        featured.category = local
        featured.save()
        html = self.client.get("/").content.decode()
        card = html[html.index('<article class="group">'):]
        card = card[:card.index("</article>")]
        self.assertIn(f"Local: {featured.title}", card)
        self.assertIn("<time", card)
        for gone in ["by ", "in <a", featured.excerpt]:
            self.assertNotIn(gone, card)
        self.assertContains(self.client.get(featured.get_absolute_url()), "Local:</span>")
        self.assertEqual(list(PostCategory.objects.values_list("name", flat=True)), ["Feature", "Local", "Event"])

        from core.models import SiteSettings
        site = SiteSettings.load()
        site.hero_video = "site/loop.mp4"
        site.save()
        html = self.client.get("/").content.decode()
        self.assertIn('<source src="/media/site/loop.mp4" type="video/mp4">', html)
        self.assertIn("data-hero-toggle", html)
        self.assertIn('href="#articles"', html)
        site.hero_video = ""
        site.save()

        from blog.models import BlogSettings
        BlogSettings.objects.update_or_create(pk=1, defaults={"posts_per_page": 3})
        html = self.client.get("/").content.decode()
        self.assertIn('aria-label="Pagination"', html)
        self.assertIn('href="?page=2"', html)
        page2 = self.client.get("/?page=2").content.decode()
        self.assertIn("Page 2", page2)
        self.assertNotIn("data-hero", page2)
        self.assertIn('class="nav-link">Store</a>', page2)

    def test_store_switched_off(self):
        from core.models import SiteSettings
        SiteSettings.objects.update_or_create(pk=1, defaults={"store_enabled": False})
        product = Product.objects.first()
        hidden = ["/shop/", "/shop/apparel/", product.get_absolute_url(), "/cart/", "/checkout/",
                  "/faq/"]
        for url in hidden:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("shop:cart_add"), {"variant": 1, "quantity": 1}).status_code, 404)

        for url in ["/", "/blog/", "/contact/", Post.objects.first().get_absolute_url()]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertNotIn('href="/shop/', html)
                self.assertNotIn('href="/cart/"', html)
                self.assertNotIn('href="/faq/"', html)
        home = self.client.get("/").content.decode()
        self.assertIn("Featured articles", home)
        self.assertIn(Post.objects.published().first().title, home)
        self.assertNotIn('name="order_number"', self.client.get("/contact/").content.decode())

        unsigned = self.client.post(reverse("shop:stripe_webhook"), "{}", content_type="application/json")
        self.assertEqual(unsigned.status_code, 400)  # reaches the webhook view instead of a 404

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/shop/").status_code, 200)
        self.assertContains(self.client.get(reverse("admin:index")), "Store hidden")

    def test_store_switch_in_admin(self):
        from core.models import SiteSettings
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("admin:core_sitesettings_changelist")),
                             reverse("admin:core_sitesettings_change", args=[1]))
        self.client.post(reverse("admin:core_sitesettings_change", args=[1]), {})
        self.assertFalse(SiteSettings.load().store_enabled)
        self.client.logout()
        self.assertEqual(self.client.get("/shop/").status_code, 404)

    def test_subscribe_and_unsubscribe(self):
        from core.models import Subscriber
        post_url = Post.objects.published().first().get_absolute_url()
        resp = self.client.post("/subscribe/", {"email": " Fan@Example.com ", "source": "popup", "next": post_url})
        self.assertRedirects(resp, post_url, fetch_redirect_response=False)
        sub = Subscriber.objects.get()
        self.assertEqual((sub.email, sub.source, sub.is_active), ("fan@example.com", "popup", True))
        html = self.client.get(post_url).content.decode()
        self.assertIn("subscribed. Thanks for following along.", html)
        self.assertNotIn("data-subscribe-popup", html)

        self.client.post("/subscribe/", {"email": "fan@example.com", "next": "/"})
        self.assertEqual(Subscriber.objects.count(), 1)
        self.client.post("/subscribe/", {"email": "bot@example.com", "website": "spam.example"})
        self.assertFalse(Subscriber.objects.filter(email="bot@example.com").exists())
        self.client.post("/subscribe/", {"email": "not-an-email"})
        self.assertEqual(Subscriber.objects.count(), 1)
        self.assertRedirects(self.client.post("/subscribe/", {"email": "x@example.com", "next": "https://evil.example/"}),
                             "/", fetch_redirect_response=False)

        url = sub.get_unsubscribe_url()
        self.assertContains(self.client.get(url), "fan@example.com")
        self.client.post(url)
        sub.refresh_from_db()
        self.assertFalse(sub.is_active)
        self.assertIsNotNone(sub.unsubscribed_at)
        self.assertEqual(self.client.get("/unsubscribe/forged-token/").status_code, 404)
        Subscriber.add("FAN@example.com", "footer")
        sub.refresh_from_db()
        self.assertTrue(sub.is_active)

    def test_subscriber_admin_export(self):
        from core.models import Subscriber
        Subscriber.add("a@example.com", "footer")
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("admin:core_subscriber_changelist"), {
            "action": "export_csv", "_selected_action": list(Subscriber.objects.values_list("pk", flat=True)),
        })
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("a@example.com", resp.content.decode())
        self.assertIn("/unsubscribe/", resp.content.decode())

    def test_admin_pages(self):
        self.client.force_login(self.admin)
        for name in ["admin:index", "admin:shop_product_changelist", "admin:shop_variant_changelist",
                     "admin:shop_order_changelist", "admin:blog_post_changelist",
                     "admin:shop_product_add", "admin:blog_post_add", "admin:blog_comment_changelist",
                     "admin:blog_mediaasset_changelist", "admin:core_subscriber_changelist"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name), follow=True).status_code, 200)
        self.assertContains(self.client.get(reverse("admin:index")), 'href="/shop/" target="_blank" rel="noopener">View store')
        product = Product.objects.first()
        self.assertEqual(self.client.get(reverse("admin:shop_product_change", args=[product.pk])).status_code, 200)
        post = Post.objects.first()
        self.assertEqual(self.client.get(reverse("admin:blog_post_change", args=[post.pk])).status_code, 200)
