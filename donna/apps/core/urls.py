from django.urls import path
from .views import InvitationAcceptView, LoginView, LogoutView, TOTPSetupView, TOTPVerifyView

app_name = "core"

urlpatterns = [
    path("login/",                     LoginView.as_view(),           name="login"),
    path("logout/",                    LogoutView.as_view(),           name="logout"),
    path("totp/",                      TOTPVerifyView.as_view(),       name="totp_verify"),
    path("totp/setup/",                TOTPSetupView.as_view(),        name="totp_setup"),
    path("invitation/<str:token>/",    InvitationAcceptView.as_view(), name="invitation_accept"),
]
