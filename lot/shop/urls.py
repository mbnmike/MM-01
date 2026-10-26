from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("shop/", views.collection, name="collection_all"),
    path("shop/<slug:category_slug>/", views.collection, name="collection"),
    path("products/<slug:slug>/", views.product_detail, name="product"),
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/<int:variant_id>/", views.cart_update, name="cart_update"),
    path("cart/remove/<int:variant_id>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/success/", views.checkout_success, name="checkout_success"),
    path("checkout/cancel/", views.checkout_cancel, name="checkout_cancel"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
]
