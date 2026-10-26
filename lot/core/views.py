from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from blog.models import BlogSettings, Post
from shop.models import Category, Order, Product

from .admin_site import LOGIN_ATTEMPTS, LOGIN_WINDOW
from .forms import ContactForm, LoginForm, RegisterForm
from .models import ContactMessage, FeaturedProduct, Review, SiteSettings
from .ratelimit import too_many

FAQS = [
    ("How long does shipping take?",
     "Orders ship in 2–4 business days. Standard delivery is 5–7 business days after that; Express is 2–3."),
    ("Do you ship internationally?",
     "Yes, to most countries we list at checkout. Duties and import taxes are paid by the customer on delivery."),
    ("How do your shirts fit?",
     "Boxy and slightly cropped. If you're between sizes or want a longer fit, size up."),
    ("Will sold-out items restock?",
     "Some do, most don't. We make small runs, so if you like something, don't wait on it."),
    ("Can I return something?",
     "Unworn apparel can be returned within 30 days. Stickers and car accessories are final sale unless they arrive damaged."),
    ("Do your plate frames fit my car?",
     "Our frames fit standard US 12 × 6 in. plates. Check your local rules — some states don't allow frames that cover text."),
    ("Is checkout secure?",
     "Payments are handled by Stripe. We never see or store your card number."),
]


def home(request):
    if not SiteSettings.load().store_enabled:
        return render(request, "core/home.html", {
            "journal": BlogSettings.load(),
            "latest_posts": Post.objects.published().select_related("author")[:6],
        })
    featured = [
        f.product
        for f in FeaturedProduct.objects.select_related("product", "product__category")
        .prefetch_related("product__images", "product__variants")
        .filter(product__is_active=True)[:8]
    ]
    if not featured:
        featured = list(Product.objects.for_listing()[:4])
    return render(
        request,
        "core/home.html",
        {
            "featured": featured,
            "reviews": Review.objects.filter(is_published=True)[:4],
            "categories": Category.objects.all(),
        },
    )


def faq(request):
    return render(request, "core/faq.html", {"faqs": FAQS})


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ContactMessage.objects.create(**form.cleaned_data)
        messages.success(request, "Message sent. We usually reply within one business day.")
        return redirect("core:contact")
    return render(request, "core/contact.html", {"form": form})


class LoginView(auth_views.LoginView):
    template_name = "account/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if too_many(request, "login", LOGIN_ATTEMPTS, LOGIN_WINDOW):
            return render(request, "429.html", status=429)
        return super().post(request, *args, **kwargs)


def register(request):
    if request.user.is_authenticated:
        return redirect("core:account")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created. Welcome in.")
        return redirect("core:account")
    return render(request, "account/register.html", {"form": form})


@login_required
def account(request):
    orders = (
        request.user.orders.exclude(status=Order.Status.CANCELLED)
        .prefetch_related(Prefetch("items"))
        .order_by("-created_at")
    )
    return render(request, "account/account.html", {"orders": orders})


@login_required
def account_order(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number, user=request.user)
    return render(request, "account/order_detail.html", {"order": order})


def preview_404(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, "404.html", status=404)
