from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("faq/", views.faq, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("subscribe/", views.subscribe, name="subscribe"),
    path("unsubscribe/<str:token>/", views.unsubscribe, name="unsubscribe"),
    path("404/", views.preview_404, name="preview_404"),
]
