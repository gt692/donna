from django.urls import path
from .views import (
    ApprovalActionView,
    ApprovalBatchView,
    ApprovalListView,
    TimeEntryCreateView,
    TimeEntryDeleteView,
    TimeEntryListView,
    TimeEntrySubmitView,
    TimeEntryUpdateView,
)

app_name = "worktrack"

urlpatterns = [
    path("",                        TimeEntryListView.as_view(),    name="list"),
    path("new/",                    TimeEntryCreateView.as_view(),  name="create"),
    path("<uuid:pk>/edit/",         TimeEntryUpdateView.as_view(),  name="edit"),
    path("<uuid:pk>/submit/",       TimeEntrySubmitView.as_view(),  name="submit"),
    path("<uuid:pk>/delete/",       TimeEntryDeleteView.as_view(),  name="delete"),
    path("approve/",                ApprovalListView.as_view(),     name="approval_list"),
    path("approve/<uuid:pk>/",      ApprovalActionView.as_view(),   name="approval_action"),
    path("approve/batch/",          ApprovalBatchView.as_view(),    name="approval_batch"),
]
