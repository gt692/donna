from django.urls import path

from .views import (
    AdminIndexView,
    CompanySettingsView,
    DashboardHomeView,
    ProductCatalogCreateView,
    ProductCatalogDeleteView,
    ProductCatalogListView,
    ProductCatalogUpdateView,
    ProjectTypeCreateView,
    ProjectTypeDeleteView,
    ProjectTypeListView,
    ProjectTypeUpdateView,
    RevenueTargetCreateView,
    RevenueTargetDeleteView,
    RevenueTargetUpdateView,
    UserCreateView,
    UserDeleteView,
    UserListView,
    UserResendInvitationView,
    UserRoleCreateView,
    UserRoleDeleteView,
    UserRoleListView,
    UserRoleReorderView,
    UserRoleUpdateView,
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

    # Rollen & Stundensätze
    path("admin/user-roles/",                 UserRoleListView.as_view(),   name="user_role_list"),
    path("admin/user-roles/reorder/",         UserRoleReorderView.as_view(), name="user_role_reorder"),
    path("admin/user-roles/new/",             UserRoleCreateView.as_view(), name="user_role_create"),
    path("admin/user-roles/<int:pk>/edit/",   UserRoleUpdateView.as_view(), name="user_role_update"),
    path("admin/user-roles/<int:pk>/delete/", UserRoleDeleteView.as_view(), name="user_role_delete"),

    # Umsatzziele (eingebettet in Firmeneinstellungen)
    path("admin/revenue-targets/new/",             RevenueTargetCreateView.as_view(), name="revenue_target_create"),
    path("admin/revenue-targets/<int:pk>/edit/",   RevenueTargetUpdateView.as_view(), name="revenue_target_edit"),
    path("admin/revenue-targets/<int:pk>/delete/", RevenueTargetDeleteView.as_view(), name="revenue_target_delete"),

    # Projekttypen
    path("admin/project-types/",                 ProjectTypeListView.as_view(),   name="project_type_list"),
    path("admin/project-types/new/",             ProjectTypeCreateView.as_view(), name="project_type_create"),
    path("admin/project-types/<int:pk>/edit/",   ProjectTypeUpdateView.as_view(), name="project_type_update"),
    path("admin/project-types/<int:pk>/delete/", ProjectTypeDeleteView.as_view(), name="project_type_delete"),

    # Produktkatalog
    path("admin/products/", ProductCatalogListView.as_view(), name="product_catalog_list"),
    path("admin/products/new/", ProductCatalogCreateView.as_view(), name="product_catalog_create"),
    path("admin/products/<int:pk>/edit/", ProductCatalogUpdateView.as_view(), name="product_catalog_update"),
    path("admin/products/<int:pk>/delete/", ProductCatalogDeleteView.as_view(), name="product_catalog_delete"),

    # Firmeneinstellungen (Singleton)
    path("admin/company-settings/", CompanySettingsView.as_view(), name="company_settings"),
]
