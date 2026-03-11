from django.urls import path

from .views import (
    EmailMFASendView,
    EmailMFAVerifyView,
    InvitationAcceptView,
    LoginView,
    LogoutView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetSentView,
    SecuritySettingsView,
    TOTPSetupView,
    TOTPVerifyView,
)

app_name = "core"

urlpatterns = [
    # Auth
    path("login/",                     LoginView.as_view(),            name="login"),
    path("logout/",                    LogoutView.as_view(),           name="logout"),
    path("totp/",                      TOTPVerifyView.as_view(),       name="totp_verify"),
    path("totp/setup/",                TOTPSetupView.as_view(),        name="totp_setup"),
    path("invitation/<str:token>/",    InvitationAcceptView.as_view(), name="invitation_accept"),

    # Password Reset
    path("password-reset/",
         PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("password-reset/sent/",
         PasswordResetSentView.as_view(),    name="password_reset_sent"),
    path("password-reset/<str:uidb64>/<str:token>/",
         PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password-reset/complete/",
         PasswordResetCompleteView.as_view(), name="password_reset_complete"),

    # E-Mail-MFA
    path("email-mfa/send/",   EmailMFASendView.as_view(),   name="email_mfa_send"),
    path("email-mfa/verify/", EmailMFAVerifyView.as_view(), name="email_mfa_verify"),

    # Profil / Sicherheitseinstellungen
    path("profile/security/", SecuritySettingsView.as_view(), name="security_settings"),
]
