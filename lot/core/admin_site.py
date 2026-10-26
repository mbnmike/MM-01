from django.conf import settings
from django.contrib import admin
from django.shortcuts import render

from .ratelimit import too_many

LOGIN_ATTEMPTS = 10
LOGIN_WINDOW = 15 * 60


class LotAdminSite(admin.AdminSite):
    site_header = f"{settings.BRAND['name']} Admin"
    site_title = f"{settings.BRAND['name']} Admin"
    index_title = "Store dashboard"

    def login(self, request, extra_context=None):
        if request.method == "POST" and too_many(request, "admin-login", LOGIN_ATTEMPTS, LOGIN_WINDOW):
            return render(request, "429.html", status=429)
        response = super().login(request, extra_context)
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
