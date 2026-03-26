from django.urls import path
from .views import (
    AbsenceApprovalActionView,
    AbsenceApprovalListView,
    AbsenceCreateView,
    AbsenceDeleteView,
    AbsenceUpdateView,
    ApprovalActionView,
    ApprovalBatchView,
    ApprovalListView,
    TeamCalendarView,
    TimeEntryCalendarAPIView,
    TimeEntryCalendarView,
    TimeEntryCreateView,
    TimeEntryDeleteView,
    TimeEntryListView,
    TimeEntrySubmitView,
    TimeEntryUpdateView,
    WorkdayLogSaveView,
)

app_name = "worktrack"

urlpatterns = [
    # Wochenübersicht
    path("",                            TimeEntryListView.as_view(),          name="list"),
    path("new/",                        TimeEntryCreateView.as_view(),        name="create"),

    # Stempeluhr
    path("log/save/",                   WorkdayLogSaveView.as_view(),         name="log_save"),

    # Abwesenheiten
    path("absences/new/",               AbsenceCreateView.as_view(),          name="absence_create"),
    path("absences/<uuid:pk>/edit/",    AbsenceUpdateView.as_view(),          name="absence_edit"),
    path("absences/<uuid:pk>/delete/",  AbsenceDeleteView.as_view(),          name="absence_delete"),
    path("absences/approve/",           AbsenceApprovalListView.as_view(),    name="absence_approval_list"),
    path("absences/approve/<uuid:pk>/", AbsenceApprovalActionView.as_view(),  name="absence_approval_action"),

    # Team-Kalender
    path("team/",                       TeamCalendarView.as_view(),           name="team_calendar"),

    # Kalender (FullCalendar, legacy)
    path("calendar/",                   TimeEntryCalendarView.as_view(),      name="calendar"),
    path("calendar/events/",            TimeEntryCalendarAPIView.as_view(),   name="calendar_events"),

    # Einzelne Buchungen
    path("<uuid:pk>/edit/",             TimeEntryUpdateView.as_view(),        name="edit"),
    path("<uuid:pk>/submit/",           TimeEntrySubmitView.as_view(),        name="submit"),
    path("<uuid:pk>/delete/",           TimeEntryDeleteView.as_view(),        name="delete"),

    # Freigabe
    path("approve/",                    ApprovalListView.as_view(),           name="approval_list"),
    path("approve/<uuid:pk>/",          ApprovalActionView.as_view(),         name="approval_action"),
    path("approve/batch/",              ApprovalBatchView.as_view(),          name="approval_batch"),
]
