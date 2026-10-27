from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from blog.models import BlogSettings, Post

from .forms import ContactForm, SubscribeForm
from .models import ContactMessage, SiteSettings, Subscriber
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
    ("How are prints made and shipped?",
     "Each print is made to order on 310 gsm archival cotton rag with pigment inks, then shipped rolled in a sturdy "
     "tube within 5–7 business days. Prints come unframed with a white border for framing."),
    ("Is checkout secure?",
     "Payments are handled by Stripe. We never see or store your card number."),
]


def home(request):
    posts = (
        Post.objects.published().select_related("category")
        .order_by("-is_featured", "-published_at", "-pk")
    )
    page = Paginator(posts, BlogSettings.load().posts_per_page).get_page(request.GET.get("page"))
    return render(request, "core/home.html", {"page": page, "site": SiteSettings.load()})


def faq(request):
    return render(request, "core/faq.html", {"faqs": FAQS})


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ContactMessage.objects.create(**form.cleaned_data)
        messages.success(request, "Message sent. We usually reply within one business day.")
        return redirect("core:contact")
    return render(request, "core/contact.html", {"form": form})


@require_POST
def subscribe(request):
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = reverse("core:home")
    if too_many(request, "subscribe", 5, 10 * 60):
        return render(request, "429.html", status=429)
    form = SubscribeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid email address.")
        return redirect(back)
    if not form.cleaned_data["website"]:
        Subscriber.add(form.cleaned_data["email"], form.cleaned_data["source"] or Subscriber.Source.FOOTER)
    request.session["subscribed"] = True
    messages.success(request, "You're subscribed. Thanks for following along.")
    return redirect(back)


def unsubscribe(request, token):
    try:
        email = signing.loads(token, salt="unsubscribe")
    except signing.BadSignature:
        raise Http404
    sub = get_object_or_404(Subscriber, email=email)
    if request.method == "POST":
        if sub.is_active:
            sub.is_active, sub.unsubscribed_at = False, timezone.now()
            sub.save(update_fields=["is_active", "unsubscribed_at"])
        request.session.pop("subscribed", None)
        return render(request, "core/unsubscribe.html", {"done": True})
    return render(request, "core/unsubscribe.html", {"sub": sub})


def preview_404(request):
    if not settings.DEBUG:
        raise Http404
    return render(request, "404.html", status=404)
