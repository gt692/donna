from django.urls import path

from .views import (
    AdminIndexView,
    DashboardHomeView,
    HourlyRateListView,
    HourlyRateUpdateView,
    LookupCreateView,
    LookupDeleteView,
    LookupListView,
    LookupUpdateView,
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

    # Lookup-Verwaltung
    path("admin/lookups/",                  LookupListView.as_view(),   name="lookup_list"),
    path("admin/lookups/new/",              LookupCreateView.as_view(), name="lookup_create"),
    path("admin/lookups/<int:pk>/edit/",    LookupUpdateView.as_view(), name="lookup_edit"),
    path("admin/lookups/<int:pk>/delete/",  LookupDeleteView.as_view(), name="lookup_delete"),

    # Stundensätze
    path("admin/hourly-rates/",             HourlyRateListView.as_view(),  name="hourly_rate_list"),
    path("admin/hourly-rates/<int:pk>/edit/", HourlyRateUpdateView.as_view(), name="hourly_rate_edit"),
]
