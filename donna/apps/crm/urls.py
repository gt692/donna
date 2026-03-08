from django.urls import path
from .views import (
    AccountCreateView, AccountDetailView, AccountListView, AccountSearchView, AccountUpdateView,
    ContactCreateView, ContactDetailView, ContactListView, ContactUpdateView,
    ContactVCardExportView, ContactVCardImportView,
    DocumentDeleteView, DocumentServeView, DocumentUploadView,
    KanbanView, ProjectKanbanMoveView,
    ProjectArchiveView, ProjectBudgetExtensionCreateView, ProjectBudgetExtensionDeleteView,
    ProjectCreateView, ProjectDetailView, ProjectListView, ProjectUpdateView,
)

app_name = "crm"

urlpatterns = [
    # Accounts
    path("accounts/search/",         AccountSearchView.as_view(), name="account_search"),
    path("accounts/",                AccountListView.as_view(),   name="account_list"),
    path("accounts/new/",            AccountCreateView.as_view(), name="account_create"),
    path("accounts/<uuid:pk>/",      AccountDetailView.as_view(), name="account_detail"),
    path("accounts/<uuid:pk>/edit/", AccountUpdateView.as_view(), name="account_edit"),

    # Kontakte
    path("contacts/",                     ContactListView.as_view(),       name="contact_list"),
    path("contacts/new/",                 ContactCreateView.as_view(),     name="contact_create"),
    path("contacts/import/",             ContactVCardImportView.as_view(), name="contact_import"),
    path("contacts/<uuid:pk>/",           ContactDetailView.as_view(),     name="contact_detail"),
    path("contacts/<uuid:pk>/edit/",      ContactUpdateView.as_view(),     name="contact_edit"),
    path("contacts/<uuid:pk>/export.vcf", ContactVCardExportView.as_view(), name="contact_vcard_export"),

    # Projekte
    path("projects/",              ProjectListView.as_view(),   name="project_list"),
    path("projects/archiv/",       ProjectArchiveView.as_view(), name="project_archive"),
    path("projects/new/",          ProjectCreateView.as_view(), name="project_create"),
    path("projects/<uuid:pk>/",    ProjectDetailView.as_view(), name="project_detail"),
    path("projects/<uuid:pk>/edit/", ProjectUpdateView.as_view(), name="project_edit"),

    # Kanban
    path("kanban/",      KanbanView.as_view(),            name="kanban"),
    path("kanban/move/", ProjectKanbanMoveView.as_view(), name="kanban_move"),

    # Dokumente
    path("projects/<uuid:pk>/documents/upload/",
         DocumentUploadView.as_view(), name="document_upload"),
    path("projects/<uuid:pk>/documents/<uuid:doc_pk>/delete/",
         DocumentDeleteView.as_view(), name="document_delete"),
    path("projects/<uuid:pk>/documents/<uuid:doc_pk>/view/",
         DocumentServeView.as_view(), name="document_serve"),

    # Budget-Erweiterungen
    path("projects/<uuid:pk>/budget-extension/add/",
         ProjectBudgetExtensionCreateView.as_view(), name="project_budget_ext_add"),
    path("projects/<uuid:pk>/budget-extension/<int:ext_pk>/delete/",
         ProjectBudgetExtensionDeleteView.as_view(), name="project_budget_ext_delete"),
]
