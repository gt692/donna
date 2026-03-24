from django.urls import path
from .views import (
    AccountCreateView, AccountDeleteView, AccountDetailView, AccountListView, AccountSearchView, AccountUpdateView,
    ContactCreateView, ContactDetailView, ContactListView, ContactUpdateView,
    ContactVCardExportView, ContactVCardImportView,
    DocumentDeleteView, DocumentServeView, DocumentUploadView,
    InvoiceCreateStandaloneView, InvoiceCreateView, InvoiceDeleteView, InvoiceDetailView, InvoiceFromOfferView,
    InvoiceListView, InvoicePDFView, InvoiceSendView, InvoiceStatusUpdateView, InvoiceUpdateView,
    InvoiceXRechnungView,
    KanbanView, ProjectKanbanMoveView,
    LeadCommissionView, LeadInquiryImportView, LeadInquiryPublicView, LeadListView,
    OfferCreateStandaloneView, OfferCreateView, OfferDeleteView, OfferDetailView, OfferListView,
    RecipientSearchView,
    TextBlockAPIView, TextBlockCreateView, TextBlockDeleteView, TextBlockListView, TextBlockUpdateView,
    OfferOrderConfirmationView, OfferPDFView, OfferSendView, OfferStatusUpdateView, OfferUpdateView,
    ProductCatalogAPIView,
    ProjectActivityCreateView, ProjectActivityDeleteView,
    ProjectArchiveView, ProjectBudgetExtensionCreateView, ProjectBudgetExtensionDeleteView,
    ProjectCreateView, ProjectDeleteView, ProjectDetailView, ProjectInvoiceCreateView, ProjectListView, ProjectUpdateView,
    QuickLeadCreateView,
)

app_name = "crm"

urlpatterns = [
    # Accounts
    path("accounts/search/",         AccountSearchView.as_view(), name="account_search"),
    path("accounts/",                AccountListView.as_view(),   name="account_list"),
    path("accounts/new/",            AccountCreateView.as_view(), name="account_create"),
    path("accounts/<uuid:pk>/",      AccountDetailView.as_view(), name="account_detail"),
    path("accounts/<uuid:pk>/edit/", AccountUpdateView.as_view(), name="account_edit"),
    path("accounts/<uuid:pk>/delete/", AccountDeleteView.as_view(), name="account_delete"),

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
    path("projects/<uuid:pk>/delete/", ProjectDeleteView.as_view(), name="project_delete"),
    path("projects/<uuid:pk>/invoice/", ProjectInvoiceCreateView.as_view(), name="project_invoice_create"),

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

    # Aktivitäten-Timeline
    path("projects/<uuid:pk>/activities/add/",
         ProjectActivityCreateView.as_view(), name="project_activity_add"),
    path("projects/<uuid:pk>/activities/<uuid:act_pk>/delete/",
         ProjectActivityDeleteView.as_view(), name="project_activity_delete"),

    # Angebote
    path("offers/new/",
         OfferCreateStandaloneView.as_view(), name="offer_create_standalone"),
    path("projects/<uuid:pk>/offers/new/",
         OfferCreateView.as_view(), name="offer_create"),
    path("offers/",
         OfferListView.as_view(), name="offer_list"),
    path("offers/<uuid:pk>/",
         OfferDetailView.as_view(), name="offer_detail"),
    path("offers/<uuid:pk>/edit/",
         OfferUpdateView.as_view(), name="offer_edit"),
    path("offers/<uuid:pk>/pdf/",
         OfferPDFView.as_view(), name="offer_pdf"),
    path("offers/<uuid:pk>/send/",
         OfferSendView.as_view(), name="offer_send"),
    path("offers/<uuid:pk>/status/",
         OfferStatusUpdateView.as_view(), name="offer_status"),
    path("offers/<uuid:pk>/delete/",
         OfferDeleteView.as_view(), name="offer_delete"),

    # Invoice URLs
    path("invoices/new/", InvoiceCreateStandaloneView.as_view(), name="invoice_create_standalone"),
    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),
    path("projects/<uuid:pk>/invoices/new/", InvoiceCreateView.as_view(), name="invoice_create"),
    path("offers/<uuid:pk>/invoice/", InvoiceFromOfferView.as_view(), name="invoice_from_offer"),
    path("invoices/<uuid:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<uuid:pk>/edit/", InvoiceUpdateView.as_view(), name="invoice_edit"),
    path("invoices/<uuid:pk>/pdf/", InvoicePDFView.as_view(), name="invoice_pdf"),
    path("invoices/<uuid:pk>/send/", InvoiceSendView.as_view(), name="invoice_send"),
    path("invoices/<uuid:pk>/status/", InvoiceStatusUpdateView.as_view(), name="invoice_status"),
    path("invoices/<uuid:pk>/delete/", InvoiceDeleteView.as_view(), name="invoice_delete"),
    path("invoices/<uuid:pk>/xrechnung/", InvoiceXRechnungView.as_view(), name="invoice_xrechnung"),
    path("offers/<uuid:pk>/ab/", OfferOrderConfirmationView.as_view(), name="offer_ab"),

    # Empfänger-Suche (Angebot/Rechnung)
    path("recipients/search/", RecipientSearchView.as_view(), name="recipient_search"),

    # Textbausteine
    path("textblocks/",              TextBlockListView.as_view(),   name="textblock_list"),
    path("textblocks/new/",          TextBlockCreateView.as_view(), name="textblock_create"),
    path("textblocks/<int:pk>/edit/", TextBlockUpdateView.as_view(), name="textblock_edit"),
    path("textblocks/<int:pk>/delete/", TextBlockDeleteView.as_view(), name="textblock_delete"),
    path("textblocks/api/",          TextBlockAPIView.as_view(),    name="textblock_api"),

    # Produktkatalog API
    path("catalog/api/", ProductCatalogAPIView.as_view(), name="catalog_api"),

    # Quick Lead
    path("quick-lead/", QuickLeadCreateView.as_view(), name="quick_lead_create"),
    path("anfrage/<uuid:token>/", LeadInquiryPublicView.as_view(), name="lead_inquiry_public"),
    path("projects/<uuid:pk>/inquiry/import/", LeadInquiryImportView.as_view(), name="lead_inquiry_import"),

    # Lead-Pipeline
    path("leads/", LeadListView.as_view(), name="lead_list"),
    path("leads/<uuid:pk>/commission/", LeadCommissionView.as_view(), name="lead_commission"),
]
