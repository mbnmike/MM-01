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
    def _checkout(self):
        self.client.post(reverse("shop:cart_add"), {"variant": self.variant.pk, "quantity": 2})
        fake = SimpleNamespace(id="cs_test_123", url="https://checkout.stripe.com/c/pay/cs_test_123")
        with mock.patch("shop.views.stripe.checkout.Session.create", return_value=fake) as create:
            resp = self.client.post(reverse("shop:checkout"), {**CHECKOUT_DATA, "shipping_method": self.ship.pk})
        return resp, create

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
            post.get_absolute_url(), "/account/login/", "/account/register/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/does-not-exist/").status_code, 404)
        self.assertRedirects(self.client.get("/journal/tag/culture/"), "/blog/tag/culture/", status_code=301)

    def test_post_has_schema_and_share_links(self):
        html = self.client.get(Post.objects.get(slug="night-meet-notes-clean-builds").get_absolute_url()).content.decode()
        self.assertIn('application/ld+json', html)
        self.assertIn('"@type": "BlogPosting"', html)
        self.assertIn("twitter.com/intent/tweet", html)
        self.assertIn("Shop the story", html)

    def test_sections_and_home(self):
        names = list(Category.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Apparel", "Car Accessories", "Accessories", "Stickers"])
        html = self.client.get("/").content.decode()
        self.assertIn('href="/shop/" class="nav-link">Store</a>', html)
        self.assertIn("Featured articles", html)
        self.assertIn("From the store", html)
        hero = Post.objects.published().filter(is_featured=True).first()
        self.assertInHTML(f'<a href="{hero.get_absolute_url()}" class="hover:underline hover:decoration-forest '
                          f'hover:decoration-[3px] hover:underline-offset-[10px]">{hero.title}</a>', html)
        self.assertNotIn("Notes from the garage", html)

        from blog.models import BlogSettings
        BlogSettings.objects.update_or_create(pk=1, defaults={"posts_per_page": 3})
        html = self.client.get("/").content.decode()
        self.assertIn('aria-label="Pagination"', html)
        self.assertIn('href="?page=2"', html)
        page2 = self.client.get("/?page=2").content.decode()
        self.assertIn("Page 2", page2)
        self.assertNotIn('aria-label="Featured post"', page2)
        self.assertNotIn("From the store", page2)
        self.assertIn('class="nav-link">Store</a>', page2)
        self.assertNotIn('name="email"', html)

    def test_store_switched_off(self):
        from core.models import SiteSettings
        SiteSettings.objects.update_or_create(pk=1, defaults={"store_enabled": False})
        product = Product.objects.first()
        hidden = ["/shop/", "/shop/apparel/", product.get_absolute_url(), "/cart/", "/checkout/",
                  "/faq/", "/account/", "/account/login/", "/account/register/"]
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
                self.assertNotIn("Shop the story", html)
        home = self.client.get("/").content.decode()
        self.assertIn("Featured articles", home)
        self.assertNotIn("From the store", home)
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

    def test_register_and_order_history(self):
        resp = self.client.post("/account/register/", {
            "username": "newbie", "email": "n@example.com", "first_name": "New",
            "password1": "a-Strong-pass-99", "password2": "a-Strong-pass-99",
        })
        self.assertRedirects(resp, "/account/")
        self.assertContains(self.client.get("/account/"), "No orders yet")

    def test_admin_pages(self):
        self.client.force_login(self.admin)
        for name in ["admin:index", "admin:shop_product_changelist", "admin:shop_variant_changelist",
                     "admin:shop_order_changelist", "admin:blog_post_changelist", "admin:core_featuredproduct_changelist",
                     "admin:shop_product_add", "admin:blog_post_add", "admin:blog_comment_changelist",
                     "admin:blog_mediaasset_changelist"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name), follow=True).status_code, 200)
        product = Product.objects.first()
        self.assertEqual(self.client.get(reverse("admin:shop_product_change", args=[product.pk])).status_code, 200)
        post = Post.objects.first()
        self.assertEqual(self.client.get(reverse("admin:blog_post_change", args=[post.pk])).status_code, 200)
