from django.conf import settings
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "catalog"
urlpatterns = [
    path("", views.home, name="home"),
    path("category/", views.all_products, name="all"),
    path("category/<path:slug_path>/", views.category_detail, name="category"),
    path("search/", views.search, name="search"),
    path("product/<int:pk>/", views.product_detail, name="product_short"),
    path("product/<int:pk>/<str:slug>/", views.product_detail, name="product"),
    path("account/wishlist/", views.wishlist_list, name="wishlist"),
    path("account/wishlist/toggle/<int:pk>/", views.wishlist_toggle, name="wishlist_toggle"),
    path("favicon.ico", RedirectView.as_view(url=settings.STATIC_URL + "img/favicon.png", permanent=True)),
]
