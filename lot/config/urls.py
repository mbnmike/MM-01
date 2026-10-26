from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from django.views.static import serve

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("blog/", include("blog.urls")),
    re_path(r"^journal/(?P<rest>.*)$", RedirectView.as_view(url="/blog/%(rest)s", permanent=True, query_string=True)),
    path("", include("shop.urls")),
    path("", include("core.urls")),
]

if settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
