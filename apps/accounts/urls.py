from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("account/login/", views.login_phone, name="login"),
    path("account/login/verify/", views.login_verify, name="verify"),
    path("account/login/resend/", views.login_resend, name="resend"),
    path("account/logout/", views.logout_view, name="logout"),
    path("account/profile/", views.profile, name="profile"),
    path("account/addresses/", views.address_list, name="addresses"),
    path("account/addresses/new/", views.address_edit, name="address_new"),
    path("account/addresses/cities/", views.address_cities, name="address_cities"),
    path("account/addresses/<int:pk>/edit/", views.address_edit, name="address_edit"),
    path("account/addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("account/addresses/<int:pk>/default/", views.address_make_default, name="address_default"),
]
