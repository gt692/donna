from django.urls import path
from .views import (
    AccountCreateView, AccountDetailView, AccountListView, AccountUpdateView,
    KanbanView,
    ProjectArchiveView, ProjectBudgetExtensionCreateView, ProjectBudgetExtensionDeleteView,
    ProjectCreateView, ProjectDetailView, ProjectListView, ProjectUpdateView,
)

app_name = "crm"

urlpatterns = [
    # Accounts
    path("accounts/",              AccountListView.as_view(),   name="account_list"),
    path("accounts/new/",          AccountCreateView.as_view(), name="account_create"),
    path("accounts/<uuid:pk>/",    AccountDetailView.as_view(), name="account_detail"),
    path("accounts/<uuid:pk>/edit/", AccountUpdateView.as_view(), name="account_edit"),

    # Projekte
    path("projects/",              ProjectListView.as_view(),   name="project_list"),
    path("projects/archiv/",       ProjectArchiveView.as_view(), name="project_archive"),
    path("projects/new/",          ProjectCreateView.as_view(), name="project_create"),
    path("projects/<uuid:pk>/",    ProjectDetailView.as_view(), name="project_detail"),
    path("projects/<uuid:pk>/edit/", ProjectUpdateView.as_view(), name="project_edit"),

    # Kanban
    path("kanban/", KanbanView.as_view(), name="kanban"),

    # Budget-Erweiterungen
    path("projects/<uuid:pk>/budget-extension/add/",
         ProjectBudgetExtensionCreateView.as_view(), name="project_budget_ext_add"),
    path("projects/<uuid:pk>/budget-extension/<int:ext_pk>/delete/",
         ProjectBudgetExtensionDeleteView.as_view(), name="project_budget_ext_delete"),
]
