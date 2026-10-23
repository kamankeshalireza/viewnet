from django.urls import path

from . import views

app_name = "orders"
urlpatterns = [
    path("checkout/", views.checkout_page, name="checkout"),
    path("checkout/coupon/", views.coupon_apply, name="coupon"),
    path("checkout/place/", views.place_order, name="place"),
    path("orders/<str:number>/", views.order_detail, name="detail"),
    path("orders/<str:number>/cancel/", views.order_cancel, name="cancel"),
    path("account/orders/", views.order_list, name="list"),
]
