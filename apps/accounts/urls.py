from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("account/login/", views.login_phone, name="login"),
    path("account/login/verify/", views.login_verify, name="verify"),
    path("account/login/resend/", views.login_resend, name="resend"),
    path("account/logout/", views.logout_view, name="logout"),
    path("account/profile/", views.profile, name="profile"),
]
