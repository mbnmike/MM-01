from django.http import Http404

from .models import SiteSettings

# Pages that only make sense with the store on. The Stripe webhook stays reachable so
# payments for orders placed before the switch still get recorded.
STORE_ONLY_CORE_VIEWS = {"faq", "account", "account_order", "register", "login"}


class StoreSwitchMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        if match is None or not is_store_page(match):
            return None
        if SiteSettings.load().store_enabled or request.user.is_staff:
            return None
        raise Http404


def is_store_page(match):
    if match.namespace == "shop":
        return match.url_name != "stripe_webhook"
    return match.namespace == "core" and match.url_name in STORE_ONLY_CORE_VIEWS
