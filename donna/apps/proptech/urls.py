from django.urls import path

from . import views

app_name = "proptech"

urlpatterns = [
    # Reports
    path("", views.PropertyReportListView.as_view(), name="report_list"),
    path("new/", views.PropertyReportCreateView.as_view(), name="report_create"),
    path("<uuid:pk>/", views.PropertyReportDetailView.as_view(), name="report_detail"),
    path("<uuid:pk>/edit/", views.PropertyReportUpdateView.as_view(), name="report_update"),
    path("<uuid:pk>/delete/", views.PropertyReportDeleteView.as_view(), name="report_delete"),
    path("<uuid:pk>/generate/", views.PropertyReportGenerateView.as_view(), name="report_generate"),
    path("<uuid:pk>/save-text/", views.PropertyReportSaveTextView.as_view(), name="report_save_text"),
    # Dateien
    path("<uuid:pk>/files/upload/", views.PropertyReportFileUploadView.as_view(), name="file_upload"),
    path("<uuid:pk>/files/<uuid:fid>/delete/", views.PropertyReportFileDeleteView.as_view(), name="file_delete"),
    # Vorlagen
    path("templates/", views.DescriptionTemplateListView.as_view(), name="template_list"),
    path("templates/new/", views.DescriptionTemplateCreateView.as_view(), name="template_create"),
    path("templates/<uuid:pk>/delete/", views.DescriptionTemplateDeleteView.as_view(), name="template_delete"),
]
