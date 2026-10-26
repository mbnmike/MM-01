from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("faq/", views.faq, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("account/", views.account, name="account"),
    path("account/orders/<str:number>/", views.account_order, name="account_order"),
    path("account/register/", views.register, name="register"),
    path("account/login/", views.LoginView.as_view(), name="login"),
    path("account/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("404/", views.preview_404, name="preview_404"),
]
