from django.urls import path

from . import views

app_name = "cart"
urlpatterns = [
    path("cart/", views.cart_detail, name="detail"),
    path("cart/add/", views.cart_add, name="add"),
    path("cart/items/<int:variant_id>/", views.cart_update, name="update"),
    path("cart/items/<int:variant_id>/remove/", views.cart_remove, name="remove"),
]
