from django.urls import path

from .views import (
    AdminIndexView,
    DashboardHomeView,
    UserCreateView,
    UserDeleteView,
    UserListView,
    UserResendInvitationView,
    UserTOTPDisableView,
    UserTOTPSetupView,
    UserToggleActiveView,
    UserUpdateView,
)

app_name = "dashboard"

urlpatterns = [
    path("", DashboardHomeView.as_view(), name="home"),

    # Administration
    path("admin/",                          AdminIndexView.as_view(),       name="admin_index"),
    path("admin/users/",                    UserListView.as_view(),         name="user_list"),
    path("admin/users/new/",               UserCreateView.as_view(),       name="user_create"),
    path("admin/users/<uuid:pk>/",         UserUpdateView.as_view(),       name="user_edit"),
    path("admin/users/<uuid:pk>/toggle/",  UserToggleActiveView.as_view(), name="user_toggle"),
    path("admin/users/<uuid:pk>/delete/",  UserDeleteView.as_view(),       name="user_delete"),
    path("admin/users/<uuid:pk>/2fa/",      UserTOTPSetupView.as_view(),         name="user_totp_setup"),
    path("admin/users/<uuid:pk>/2fa/off/",  UserTOTPDisableView.as_view(),       name="user_totp_disable"),
    path("admin/users/<uuid:pk>/reinvite/", UserResendInvitationView.as_view(),  name="user_reinvite"),
]
