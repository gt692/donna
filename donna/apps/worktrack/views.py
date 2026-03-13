"""
worktrack/views.py

Zeiterfassungs-UI:
  /worktrack/                   → Wochenübersicht eigener Buchungen
  /worktrack/new/               → Neue Buchung erstellen
  /worktrack/<id>/edit/         → Entwurf bearbeiten
  /worktrack/<id>/submit/       → Einreichen (POST)
  /worktrack/<id>/delete/       → Löschen (nur Entwürfe, POST)
  /worktrack/approve/           → Freigabe-Liste (Teamleiter/Admin)
  /worktrack/approve/<id>/      → Einzelfreigabe oder Ablehnung
"""
from __future__ import annotations

import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from .forms import ApprovalRejectForm, TimeEntryForm
from .models import TimeEntry


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class WorktrackMixin(LoginRequiredMixin):
    login_url = "/auth/login/"

    def get_week_bounds(self, offset: int = 0):
        """Gibt (montag, sonntag) der aktuellen Woche ± offset zurück."""
        today    = timezone.now().date()
        monday   = today - datetime.timedelta(days=today.weekday()) + datetime.timedelta(weeks=offset)
        sunday   = monday + datetime.timedelta(days=6)
        return monday, sunday


# ---------------------------------------------------------------------------
# Wochenübersicht
# ---------------------------------------------------------------------------

class TimeEntryListView(WorktrackMixin, TemplateView):
    template_name = "worktrack/list.html"

    def get_context_data(self, **kwargs):
        ctx    = super().get_context_data(**kwargs)
        user   = self.request.user
        offset = int(self.request.GET.get("week", 0))
        monday, sunday = self.get_week_bounds(offset)

        entries = (
            TimeEntry.objects
            .filter(user=user, date__range=(monday, sunday))
            .select_related("project", "project__account")
            .order_by("date", "start_time")
        )

        # Stunden pro Tag gruppieren
        days = []
        for i in range(7):
            day     = monday + datetime.timedelta(days=i)
            day_entries = [e for e in entries if e.date == day]
            day_total   = sum(float(e.duration_hours) for e in day_entries)
            days.append({"date": day, "entries": day_entries, "total": day_total})

        week_total = sum(float(e.duration_hours) for e in entries)
        approved   = sum(float(e.duration_hours) for e in entries if e.status == TimeEntry.Status.APPROVED)
        pending    = sum(float(e.duration_hours) for e in entries if e.status == TimeEntry.Status.SUBMITTED)

        ctx.update({
            "days":        days,
            "week_total":  week_total,
            "approved_h":  approved,
            "pending_h":   pending,
            "week_offset": offset,
            "monday":      monday,
            "sunday":      sunday,
            "prev_offset": offset - 1,
            "next_offset": offset + 1,
            "is_current_week": offset == 0,
        })
        return ctx


# ---------------------------------------------------------------------------
# Neue Buchung
# ---------------------------------------------------------------------------

class TimeEntryCreateView(WorktrackMixin, CreateView):
    template_name = "worktrack/form.html"
    form_class    = TimeEntryForm

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        entry      = form.save(commit=False)
        entry.user = self.request.user
        entry.save()
        if self.request.POST.get("action") == "save_and_submit":
            try:
                entry.submit()
                messages.success(self.request, "Buchung gespeichert und eingereicht.")
            except ValueError:
                messages.success(self.request, "Buchung gespeichert.")
        else:
            messages.success(self.request, "Buchung gespeichert.")
        return redirect("worktrack:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Neue Zeitbuchung"
        ctx["submit_label"] = "Speichern"
        return ctx


# ---------------------------------------------------------------------------
# Buchung bearbeiten (nur Entwürfe)
# ---------------------------------------------------------------------------

class TimeEntryUpdateView(WorktrackMixin, UpdateView):
    template_name = "worktrack/form.html"
    form_class    = TimeEntryForm

    def get_queryset(self):
        return TimeEntry.objects.filter(user=self.request.user, status=TimeEntry.Status.DRAFT)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Buchung aktualisiert.")
        return redirect("worktrack:list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Buchung bearbeiten"
        ctx["submit_label"] = "Speichern"
        return ctx


# ---------------------------------------------------------------------------
# Einreichen
# ---------------------------------------------------------------------------

class TimeEntrySubmitView(WorktrackMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(TimeEntry, pk=pk, user=request.user)
        try:
            entry.submit()
            messages.success(request, f"Buchung vom {entry.date} eingereicht.")
        except ValueError as e:
            messages.error(request, str(e))
        return redirect("worktrack:list")


# ---------------------------------------------------------------------------
# Löschen (nur Entwürfe)
# ---------------------------------------------------------------------------

class TimeEntryDeleteView(WorktrackMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(TimeEntry, pk=pk, user=request.user)
        if entry.status != TimeEntry.Status.DRAFT:
            messages.error(request, "Nur Entwürfe können gelöscht werden.")
            return redirect("worktrack:list")
        date = entry.date
        entry.delete()
        messages.success(request, f"Buchung vom {date} gelöscht.")
        return redirect("worktrack:list")


# ---------------------------------------------------------------------------
# Freigabe-Liste (Teamleiter / Admin)
# ---------------------------------------------------------------------------

class ApprovalListView(WorktrackMixin, UserPassesTestMixin, TemplateView):
    template_name = "worktrack/approval_list.html"

    def test_func(self):
        return self.request.user.can_approve_time_entries()

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        user = self.request.user

        approvable_users = user.get_approvable_users()
        pending = (
            TimeEntry.objects
            .filter(status=TimeEntry.Status.SUBMITTED, user__in=approvable_users)
            .select_related("user", "project", "project__account")
            .order_by("date", "user__last_name")
        )

        # Nach Mitarbeiter gruppieren für übersichtliche Darstellung
        by_user: dict = {}
        for entry in pending:
            uid = entry.user_id
            if uid not in by_user:
                by_user[uid] = {"user": entry.user, "entries": [], "total": 0}
            by_user[uid]["entries"].append(entry)
            by_user[uid]["total"] += float(entry.duration_hours)

        ctx["groups"]        = list(by_user.values())
        ctx["pending_count"] = pending.count()
        ctx["reject_form"]   = ApprovalRejectForm()
        return ctx


# ---------------------------------------------------------------------------
# Freigabe-Aktion (approve / reject)
# ---------------------------------------------------------------------------

class ApprovalActionView(WorktrackMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.can_approve_time_entries()

    def post(self, request, pk):
        user  = request.user
        entry = get_object_or_404(TimeEntry, pk=pk)

        # Sicherstellen dass der Approver berechtigt ist
        if entry.user not in user.get_approvable_users() and not user.is_admin:
            return HttpResponseForbidden()

        action = request.POST.get("action")

        if action == "approve":
            try:
                entry.approve(reviewer=user)
                messages.success(
                    request,
                    f"Buchung von {entry.user.get_full_name()} ({entry.duration_hours} h) freigegeben."
                )
            except ValueError as e:
                messages.error(request, str(e))

        elif action == "reject":
            form = ApprovalRejectForm(request.POST)
            if form.is_valid():
                try:
                    entry.reject(reviewer=user, note=form.cleaned_data["review_note"])
                    messages.warning(
                        request,
                        f"Buchung von {entry.user.get_full_name()} abgelehnt."
                    )
                except ValueError as e:
                    messages.error(request, str(e))
            else:
                messages.error(request, "Bitte eine Begründung angeben (mind. 10 Zeichen).")

        return redirect("worktrack:approval_list")


# ---------------------------------------------------------------------------
# Batch-Freigabe: alle Einträge eines Mitarbeiters auf einmal
# ---------------------------------------------------------------------------

class ApprovalBatchView(WorktrackMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.can_approve_time_entries()

    def post(self, request):
        user         = request.user
        entry_ids    = request.POST.getlist("entry_ids")
        approvable   = user.get_approvable_users()

        approved_count = 0
        for eid in entry_ids:
            try:
                entry = TimeEntry.objects.get(
                    pk=eid, status=TimeEntry.Status.SUBMITTED, user__in=approvable
                )
                entry.approve(reviewer=user)
                approved_count += 1
            except (TimeEntry.DoesNotExist, ValueError):
                continue

        if approved_count:
            messages.success(request, f"{approved_count} Buchung(en) freigegeben.")
        return redirect("worktrack:approval_list")


# ---------------------------------------------------------------------------
# Kalender-Ansicht
# ---------------------------------------------------------------------------

class TimeEntryCalendarView(LoginRequiredMixin, TemplateView):
    login_url     = "/auth/login/"
    template_name = "worktrack/calendar.html"


class TimeEntryCalendarAPIView(LoginRequiredMixin, View):
    login_url = "/auth/login/"

    def get(self, request):
        start_str = request.GET.get("start", "")
        end_str   = request.GET.get("end",   "")

        try:
            start = datetime.date.fromisoformat(start_str[:10])
            end   = datetime.date.fromisoformat(end_str[:10])
        except (ValueError, TypeError):
            return JsonResponse([], safe=False)

        entries = (
            TimeEntry.objects
            .filter(user=request.user, date__range=(start, end))
            .select_related("project")
        )

        status_colors = {
            TimeEntry.Status.APPROVED:  "#16a34a",
            TimeEntry.Status.SUBMITTED: "#d97706",
        }

        events = []
        for entry in entries:
            color = status_colors.get(entry.status, "#64748b")

            if entry.start_time:
                start_val = f"{entry.date}T{entry.start_time.strftime('%H:%M:%S')}"
            else:
                start_val = str(entry.date)

            events.append({
                "id":    str(entry.id),
                "title": f"{entry.project.name} · {entry.duration_hours}h",
                "start": start_val,
                "color": color,
                "extendedProps": {
                    "description":    entry.description,
                    "status":         entry.status,
                    "duration_hours": float(entry.duration_hours),
                },
            })

        return JsonResponse(events, safe=False)
