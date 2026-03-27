"""
crm/views.py

Account- und Projekt-Verwaltung.

URLs:
  /crm/accounts/               → AccountListView
  /crm/accounts/new/           → AccountCreateView
  /crm/accounts/<pk>/          → AccountDetailView
  /crm/accounts/<pk>/edit/     → AccountUpdateView

  /crm/projects/               → ProjectListView
  /crm/projects/new/           → ProjectCreateView
  /crm/projects/<pk>/          → ProjectDetailView
  /crm/projects/<pk>/edit/     → ProjectUpdateView
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

import datetime
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.mail import EmailMessage
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from .forms import AccountForm, ContactForm, InvoiceForm, InvoiceItemForm, InvoiceItemFormSet, OfferForm, OfferItemFormSet, ProjectForm, TextBlockForm, UnitForm
from .models import Account, Contact, Document, Invoice, InvoiceItem, LeadInquiry, Offer, OfferItem, Project, ProjectActivity, ProjectBudgetExtension, ProjectMemberRate, TextBlock, Unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _company_ctx():
    """Build template context dict with company settings + logo data URI."""
    from apps.core.models import CompanySettings
    import base64, mimetypes
    cs = CompanySettings.get()
    logo_data_uri = None
    if cs.logo and cs.logo.name:
        try:
            with open(cs.logo.path, "rb") as f:
                raw = f.read()
            mime = mimetypes.guess_type(cs.logo.name)[0] or "image/png"
            logo_data_uri = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        except (OSError, ValueError):
            pass
    return {"company_settings": cs, "company_logo_uri": logo_data_uri}


def _build_email(subject: str, text_body: str, to: list[str]) -> EmailMessage:
    """
    Erstellt eine HTML-E-Mail mit Firmenlogo und Signatur aus CompanySettings.
    text_body: Reiner Text-Inhalt (wird in <p>-Blöcke umgewandelt).
    """
    import base64, mimetypes
    from django.conf import settings as dj_settings
    from apps.core.models import CompanySettings

    cs = CompanySettings.get()
    sender_name = cs.company_name or dj_settings.MS_SENDER_EMAIL
    from_email = f"{sender_name} <{dj_settings.MS_SENDER_EMAIL}>"

    # Logo als Base64 Data-URI
    logo_html = ""
    if cs.logo and cs.logo.name:
        try:
            with open(cs.logo.path, "rb") as f:
                raw = f.read()
            mime = mimetypes.guess_type(cs.logo.name)[0] or "image/png"
            logo_data_uri = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
            logo_html = (
                f'<img src="{logo_data_uri}" alt="{cs.company_name}" height="48" '
                f'style="height:48px;max-width:220px;width:auto;display:block;">'
            )
        except (OSError, ValueError):
            pass

    # Signaturzeilen
    sig_parts = []
    if cs.company_name:
        sig_parts.append(f"<strong>{cs.company_name}{'&nbsp;' + cs.legal_form if cs.legal_form else ''}</strong>")
    addr_parts = [p for p in [cs.street, f"{cs.postal_code} {cs.city}".strip()] if p]
    if addr_parts:
        sig_parts.append(" · ".join(addr_parts))
    if cs.phone:
        sig_parts.append(f"Tel.: {cs.phone}")
    primary = cs.primary_color or "#2F6FB3"
    if cs.email:
        sig_parts.append(f'<a href="mailto:{cs.email}" style="color:{primary};text-decoration:none;">{cs.email}</a>')
    if cs.website:
        sig_parts.append(f'<a href="{cs.website}" style="color:{primary};text-decoration:none;">{cs.website}</a>')

    sig_html = "<br>".join(sig_parts)

    # Text in Absätze umwandeln
    paragraphs = "".join(
        f"<p style='margin:0 0 12px 0;'>{line.replace(chr(10), '<br>')}</p>"
        for line in text_body.split("\n\n") if line.strip()
    )

    primary = cs.primary_color or "#2F6FB3"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);">
        <!-- Header -->
        <tr><td style="background:{primary};padding:24px 32px;">
          {logo_html if logo_html else f'<span style="color:#fff;font-size:18px;font-weight:700;">{cs.company_name}</span>'}
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:32px;color:#1e293b;font-size:14px;line-height:1.6;">
          {paragraphs}
        </td></tr>
        <!-- Signatur -->
        <tr><td style="padding:20px 32px 28px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;line-height:1.8;">
          {sig_html}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""

    msg = EmailMessage(subject=subject, body=html, from_email=from_email, to=to)
    msg.content_subtype = "html"
    return msg


def _all_projects_list(exclude_pk=None) -> list:
    qs = Project.objects.order_by("name")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return [{"id": str(p.pk), "label": str(p)} for p in qs]


def _member_rates_data(form, project=None) -> dict:
    """Baut ein Dict {user_pk: {name, role, default_rate, current_rate}} für das Template."""
    from apps.core.models import UserRole
    role_labels = dict(UserRole.objects.values_list("slug", "name"))
    data = {}
    for user in form.fields["team_members"].queryset:
        data[str(user.pk)] = {
            "name": user.get_full_name() or user.username,
            "role": role_labels.get(user.role, user.role),
            "default_rate": float(user.default_hourly_rate) if user.default_hourly_rate is not None else None,
            "current_rate": None,
        }
    if project and project.pk:
        for mr in project.member_rates.select_related("user"):
            key = str(mr.user_id)
            if key in data:
                data[key]["current_rate"] = float(mr.hourly_rate)
    return data


def _save_member_rates(request, project, team_members) -> None:
    """Speichert/aktualisiert projektspezifische Stundensätze der Teammitglieder."""
    team_pks = [u.pk for u in team_members]
    project.member_rates.exclude(user_id__in=team_pks).delete()
    for user in team_members:
        raw = request.POST.get(f"member_rate_{user.pk}", "").strip()
        try:
            rate = Decimal(raw)
        except InvalidOperation:
            default = user.default_hourly_rate
            if default is None:
                continue
            rate = Decimal(str(default))
        ProjectMemberRate.objects.update_or_create(
            project=project, user=user, defaults={"hourly_rate": rate}
        )


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class CRMMixin(LoginRequiredMixin):
    login_url = "/auth/login/"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["overdue_invoices_count"] = Invoice.objects.filter(
            status=Invoice.Status.SENT, due_date__lt=date.today()
        ).count()
        return ctx


class AdminOrLeadMixin(CRMMixin, UserPassesTestMixin):
    """Legacy-Alias — wird schrittweise durch spezifische Mixins ersetzt."""
    def test_func(self):
        return self.request.user.can_approve_time_entries()


def _make_perm_mixin(perm_attr: str):
    """Factory für View-Mixins, die ein einzelnes can_* Property prüfen."""
    class _Mixin(CRMMixin, UserPassesTestMixin):
        def test_func(self):
            return bool(getattr(self.request.user, perm_attr, False))
        def handle_no_permission(self):
            if not self.request.user.is_authenticated:
                return redirect(self.login_url)
            messages.error(self.request, "Keine Berechtigung für diese Aktion.")
            return redirect("dashboard:home")
    _Mixin.__name__ = f"Perm_{perm_attr}"
    return _Mixin


EditLeadsMixin      = _make_perm_mixin("can_edit_leads")
DeleteLeadsMixin    = _make_perm_mixin("can_delete_leads")
EditProjectsMixin   = _make_perm_mixin("can_edit_projects")
DeleteProjectsMixin = _make_perm_mixin("can_delete_projects")
EditOffersMixin     = _make_perm_mixin("can_edit_offers")
DeleteOffersMixin   = _make_perm_mixin("can_delete_offers")
SendOffersMixin     = _make_perm_mixin("can_send_offers")
EditInvoicesMixin   = _make_perm_mixin("can_edit_invoices")
DeleteInvoicesMixin = _make_perm_mixin("can_delete_invoices")
SendInvoicesMixin   = _make_perm_mixin("can_send_invoices")
EditAccountsMixin   = _make_perm_mixin("can_edit_accounts")
DeleteAccountsMixin = _make_perm_mixin("can_delete_accounts")
ApproveTimeMixin    = _make_perm_mixin("can_approve_time")
EditTemplatesMixin  = _make_perm_mixin("can_edit_templates")


# ---------------------------------------------------------------------------
# Account-Views
# ---------------------------------------------------------------------------

def _save_inline_contact(request, account):
    """Legt einen neuen Kontakt an und setzt ihn als primary_contact, wenn
    new_contact_first_name oder new_contact_last_name im POST vorhanden sind."""
    fn = request.POST.get("new_contact_first_name", "").strip()
    ln = request.POST.get("new_contact_last_name", "").strip()
    if not (fn or ln):
        return
    contact = Contact.objects.create(
        first_name=fn,
        last_name=ln,
        email=request.POST.get("new_contact_email", "").strip(),
        phone=request.POST.get("new_contact_phone", "").strip(),
        mobile=request.POST.get("new_contact_mobile", "").strip(),
    )
    contact.accounts.add(account)
    account.primary_contact = contact
    account.save(update_fields=["primary_contact"])


class AccountListView(CRMMixin, ListView):
    model               = Account
    template_name       = "crm/account_list.html"
    context_object_name = "accounts"
    paginate_by         = 25

    def get_queryset(self):
        qs = (
            Account.objects
            .filter(is_active=True)
            .annotate(project_count=Count("projects"))
            .select_related("account_manager")
            .order_by("name")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        t = self.request.GET.get("type", "")
        if t:
            qs = qs.filter(account_type=t)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]            = self.request.GET.get("q", "")
        ctx["type_filter"]  = self.request.GET.get("type", "")
        ctx["account_types"] = Account.AccountType.choices
        return ctx


class AccountCreateView(EditAccountsMixin, CreateView):
    model         = Account
    form_class    = AccountForm
    template_name = "crm/account_form.html"

    def form_valid(self, form):
        account = form.save()
        _save_inline_contact(self.request, account)
        messages.success(self.request, f'Account „{account.name}" wurde erstellt.')
        return redirect("crm:account_detail", pk=account.pk)

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]           = "Neuer Account"
        ctx["submit_label"]         = "Account erstellen"
        ctx["contact_emails"]       = {str(k): v for k, v in Contact.objects.values_list("id", "email")}
        ctx["google_maps_api_key"]  = dj_settings.GOOGLE_MAPS_API_KEY
        return ctx


class AccountQuickCreateView(EditAccountsMixin, View):
    """Minimal Account-Erstellung via AJAX — gibt JSON zurück für Modal im Angebotsformular."""

    def post(self, request):
        account_type  = request.POST.get("account_type", Account.AccountType.COMPANY)
        email         = request.POST.get("email", "").strip()
        phone         = request.POST.get("phone", "").strip()
        address_line1 = request.POST.get("address_line1", "").strip()
        postal_code   = request.POST.get("postal_code", "").strip()
        city          = request.POST.get("city", "").strip()

        is_private = account_type == Account.AccountType.PRIVATE
        if is_private:
            first_name  = request.POST.get("first_name", "").strip()
            last_name   = request.POST.get("last_name", "").strip()
            first_name2 = request.POST.get("first_name2", "").strip()
            last_name2  = request.POST.get("last_name2", "").strip()
            person1 = f"{first_name} {last_name}".strip()
            person2 = f"{first_name2} {last_name2}".strip()
            name = f"{person1} & {person2}" if person2 else person1
        else:
            name = request.POST.get("name", "").strip()

        if not name:
            return JsonResponse({"error": "Name ist erforderlich."}, status=400)

        account = Account.objects.create(
            name=name,
            account_type=account_type,
            email=email,
            phone=phone,
            address_line1=address_line1,
            postal_code=postal_code,
            city=city,
        )

        address_parts = [p for p in [address_line1, f"{postal_code} {city}".strip()] if p]
        return JsonResponse({
            "id":      str(account.pk),
            "name":    account.name,
            "number":  account.account_number,
            "email":   account.email or "",
            "address": "\n".join(address_parts),
            "type":    account.account_type,
            "label":   account.name,
        })


class AccountDetailView(CRMMixin, DetailView):
    model         = Account
    template_name = "crm/account_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["projects"] = (
            self.object.projects
            .select_related("team_lead")
            .order_by("-created_at")
        )
        return ctx


class AccountUpdateView(EditAccountsMixin, UpdateView):
    model         = Account
    form_class    = AccountForm
    template_name = "crm/account_form.html"

    def form_valid(self, form):
        account = form.save()
        _save_inline_contact(self.request, account)
        messages.success(self.request, f'Account „{account.name}" wurde aktualisiert.')
        return redirect("crm:account_detail", pk=account.pk)

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]           = f"{self.object.name} bearbeiten"
        ctx["submit_label"]         = "Speichern"
        ctx["contact_emails"]       = {str(k): v for k, v in Contact.objects.values_list("id", "email")}
        ctx["google_maps_api_key"]  = dj_settings.GOOGLE_MAPS_API_KEY
        return ctx


class AccountDeleteView(DeleteAccountsMixin, View):
    """Confirmation + soft-delete for Account."""

    def _context(self, account):
        projects = account.projects.all()
        offer_count   = sum(p.offers.count()   for p in projects)
        invoice_count = sum(p.invoices.count() for p in projects)
        return {
            "account": account,
            "project_count": projects.count(),
            "offer_count": offer_count,
            "invoice_count": invoice_count,
        }

    def get(self, request, pk):
        account = get_object_or_404(Account, pk=pk)
        return render(request, "crm/account_confirm_delete.html", self._context(account))

    def post(self, request, pk):
        account = get_object_or_404(Account, pk=pk)
        name = account.name
        keep = request.POST.get("action") == "keep_projects"
        account.delete(keep_projects=keep)
        if keep:
            messages.success(request, f'Account „{name}" wurde gelöscht. Die Projekte bleiben erhalten.')
        else:
            messages.success(request, f'Account „{name}" und alle zugehörigen Projekte wurden gelöscht.')
        return redirect("crm:account_list")


# ---------------------------------------------------------------------------
# Projekt-Views
# ---------------------------------------------------------------------------

class ProjectListView(CRMMixin, ListView):
    model               = Project
    template_name       = "crm/project_list.html"
    context_object_name = "projects"
    paginate_by         = 25

    def _base_qs(self):
        return Project.objects.all().select_related("account", "team_lead")

    def get_queryset(self):
        qs = self._base_qs().exclude(status__in=Project.ARCHIVED_STATUSES).order_by("-created_at")

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(account__name__icontains=q)

        status = self.request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)

        if self.request.GET.get("mine") == "1":
            user = self.request.user
            qs = qs.filter(
                Q(team_lead=user) | Q(team_members=user)
            )

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]             = self.request.GET.get("q", "")
        ctx["status_filter"] = self.request.GET.get("status", "")
        ctx["mine_filter"]   = self.request.GET.get("mine", "")
        ctx["status_choices"] = [
            (v, l) for v, l in Project.Status.choices
            if v not in Project.ARCHIVED_STATUSES
        ]
        ctx["archive_count"] = self._base_qs().filter(
            status__in=Project.ARCHIVED_STATUSES
        ).count()
        return ctx


class ProjectArchiveView(CRMMixin, TemplateView):
    template_name = "crm/project_archive.html"

    def _base_qs(self):
        return Project.objects.all().select_related("account", "team_lead")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self._base_qs()
        ctx["completed_projects"] = base.filter(
            status=Project.Status.COMPLETED
        ).order_by("-updated_at")
        ctx["cancelled_projects"] = base.filter(
            status=Project.Status.CANCELLED
        ).order_by("-updated_at")
        ctx["offer_lost_projects"] = base.filter(
            status=Project.Status.OFFER_LOST
        ).order_by("-updated_at")
        return ctx


class ProjectCreateView(EditProjectsMixin, CreateView):
    model         = Project
    form_class    = ProjectForm
    template_name = "crm/project_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        project = form.save(commit=False)
        project.created_by = self.request.user
        project.status = Project.Status.LEAD  # neue Projekte immer als Lead

        # Inline-Account anlegen falls kein bestehender ausgewählt
        if not project.account_id:
            new_name = self.request.POST.get("new_account_name", "").strip()
            new_type = self.request.POST.get("new_account_type", Account.AccountType.COMPANY)
            if new_name:
                project.account = Account.objects.create(
                    name=new_name,
                    account_type=new_type,
                )
            else:
                form.add_error(None, "Bitte einen Account auswählen oder einen neuen Namen eingeben.")
                return self.form_invalid(form)

        project.save()
        form.save_m2m()
        _save_member_rates(self.request, project, form.cleaned_data["team_members"])
        messages.success(self.request, f'Projekt „{project.name}" wurde erstellt.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]      = "Neues Projekt"
        ctx["submit_label"]    = "Projekt erstellen"
        ctx["is_create"]       = True
        ctx["account_types"]   = Account.AccountType.choices
        form = kwargs.get("form") or ctx.get("form")
        if form:
            ctx["member_rates_data"] = _member_rates_data(form, project=None)
        ctx["all_projects_json"] = _all_projects_list()
        ctx["selected_predecessors_json"] = []
        return ctx


class AccountSearchView(CRMMixin, View):
    """AJAX: Accounts per Name suchen (für Projekt-Anlage-Widget)."""

    def get(self, request):
        q = request.GET.get("q", "").strip()
        qs = Account.objects.filter(is_active=True)
        if q:
            qs = qs.filter(name__icontains=q)
        results = [{"id": str(a.pk), "name": a.name, "type": a.get_account_type_display()}
                   for a in qs.order_by("name")[:10]]
        return JsonResponse({"results": results})


class RecipientSearchView(CRMMixin, View):
    """AJAX: Accounts für Empfänger-Autocomplete in Angebot/Rechnung."""

    def get(self, request):
        q = request.GET.get("q", "").strip()
        results = []

        if q:
            accounts = (
                Account.objects
                .filter(is_active=True)
                .filter(
                    Q(name__icontains=q) | Q(email__icontains=q) |
                    Q(billing_email__icontains=q) | Q(account_number__icontains=q)
                )
                .order_by("name")[:12]
            )
            TYPE_LABELS = {
                "private":  "Privatperson",
                "company":  "Unternehmen",
                "estate":   "Erbengemeinschaft",
                "internal": "Intern",
            }
            for a in accounts:
                address_parts = []
                if a.address_line1:
                    address_parts.append(a.address_line1)
                if a.address_line2:
                    address_parts.append(a.address_line2)
                if a.postal_code or a.city:
                    address_parts.append(f"{a.postal_code} {a.city}".strip())
                results.append({
                    "id":           str(a.pk),
                    "type":         a.account_type,
                    "type_label":   TYPE_LABELS.get(a.account_type, a.account_type),
                    "label":        a.name,
                    "number":       a.account_number,
                    "name":         a.name,
                    "email":        a.billing_email or a.email,
                    "address":      "\n".join(address_parts),
                })

        return JsonResponse({"results": results})


class ProjectDetailView(CRMMixin, DetailView):
    model         = Project
    template_name = "crm/project_detail.html"

    def get_context_data(self, **kwargs):
        ctx     = super().get_context_data(**kwargs)
        project = self.object

        from apps.worktrack.models import TimeEntry
        entries = (
            TimeEntry.objects
            .filter(project=project)
            .select_related("user")
            .order_by("-date")[:20]
        )

        # Stunden-Statistik
        stats = TimeEntry.objects.filter(project=project).aggregate(
            total=Sum("duration_hours"),
            approved=Sum("duration_hours", filter=__import__("django.db.models", fromlist=["Q"]).Q(status="approved")),
        )
        hours_total    = float(stats["total"] or 0)
        hours_approved = float(stats["approved"] or 0)

        # Kosten: freigegebene Stunden × projektspezifischer Stundensatz je Mitglied
        rates_map = {str(mr.user_id): float(mr.hourly_rate) for mr in project.member_rates.all()}
        approved_entries = (
            TimeEntry.objects
            .filter(project=project, status="approved")
            .values("user_id", "duration_hours")
        )
        cost_approved = sum(
            float(e["duration_hours"]) * rates_map.get(str(e["user_id"]), 0)
            for e in approved_entries
        )

        extensions = list(project.budget_extensions.all())
        base_budget      = float(project.budget_amount) if project.budget_amount else None
        extra_budget     = sum(float(e.amount) for e in extensions)
        budget_amount    = (base_budget + extra_budget) if base_budget is not None else None
        budget_cost_pct  = min(int(cost_approved / budget_amount * 100), 100) if budget_amount else None
        budget_remaining = budget_amount - cost_approved if budget_amount is not None else None

        # Team-Mitglieder mit Stundensatz für Template aufbereiten
        team_members_with_rates = [
            {
                "member": m,
                "rate": rates_map.get(str(m.pk)),
            }
            for m in project.team_members.all()
        ]

        # Provisions-Berechnung (nur Projekttyp "sale")
        commission_net   = None
        commission_gross = None
        if project.project_type == "sale" and project.purchase_price:
            inner = float(project.commission_inner or 0)
            outer = float(project.commission_outer or 0)
            commission_net   = float(project.purchase_price) * (inner + outer) / 100
            commission_gross = commission_net * 1.19

        ctx["commission_net"]          = commission_net
        ctx["commission_gross"]        = commission_gross
        ctx["time_entries"]            = entries
        ctx["hours_total"]             = hours_total
        ctx["hours_approved"]          = hours_approved
        ctx["cost_approved"]           = cost_approved
        ctx["has_rates"]               = bool(rates_map)
        ctx["budget_amount_total"]     = budget_amount
        ctx["budget_cost_pct"]         = budget_cost_pct
        ctx["budget_remaining"]        = budget_remaining
        ctx["budget_extensions"]       = extensions
        ctx["documents"]               = project.documents.order_by("-document_date")
        ctx["team_members"]            = project.team_members.all()
        ctx["team_members_with_rates"] = team_members_with_rates
        ctx["budget_pct"]              = (
            min(int(hours_approved / float(project.budget_hours) * 100), 100)
            if project.budget_hours else None
        )
        ctx["today"]                   = datetime.date.today().isoformat()
        ctx["activities"]              = project.activities.select_related("created_by").order_by("-occurred_at")[:50]
        ctx["activity_types"]          = ProjectActivity.ActivityType.choices
        ctx["invoices"]                = project.invoices.all()

        # Prozess-Pipeline Stepper
        s = project.status
        S = Project.Status
        steps = [
            ("Lead",          s not in {"lead"},                                              s == "lead"),
            ("Angebot",       s in {"active","on_hold","invoiced","completed","cancelled"},   s == "offer_sent"),
            ("Beauftragt",    s in {"invoiced","completed"},                                  s == "active"),
            ("Rechnung",      s == "completed",                                               s == "invoiced"),
            ("Abgeschlossen", False,                                                          s == "completed"),
        ]
        ctx["process_steps"] = [(label, "", done, active) for label, done, active in steps]

        try:
            ctx["lead_inquiry"] = project.lead_inquiry
        except Exception:
            ctx["lead_inquiry"] = None

        return ctx


class ProjectUpdateView(EditProjectsMixin, UpdateView):
    model         = Project
    form_class    = ProjectForm
    template_name = "crm/project_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        project = form.save()
        _save_member_rates(self.request, project, form.cleaned_data["team_members"])
        messages.success(self.request, f'Projekt „{project.name}" wurde aktualisiert.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"{self.object.name} bearbeiten"
        ctx["submit_label"] = "Speichern"
        form = kwargs.get("form") or ctx.get("form")
        if form:
            ctx["member_rates_data"] = _member_rates_data(form, project=self.object)
        ctx["all_projects_json"] = _all_projects_list(exclude_pk=self.object.pk)
        ctx["selected_predecessors_json"] = [
            {"id": str(p.pk), "label": str(p)}
            for p in self.object.predecessor_projects.all()
        ]
        return ctx


class ProjectDeleteView(DeleteProjectsMixin, View):
    """Confirmation + soft-delete for Project (cascades to open offers/invoices)."""

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        offer_count   = project.offers.count()
        invoice_count = project.invoices.count()
        return render(request, "crm/project_confirm_delete.html", {
            "project": project,
            "offer_count": offer_count,
            "invoice_count": invoice_count,
            "cancel_url": request.GET.get("next") or reverse("crm:project_detail", kwargs={"pk": pk}),
        })

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        name = project.name
        project.delete()
        messages.success(request, f'Projekt „{name}" wurde gelöscht.')
        return redirect("crm:project_list")


# ---------------------------------------------------------------------------
# Budget-Erweiterung hinzufügen (POST-only)
# ---------------------------------------------------------------------------

class ProjectBudgetExtensionCreateView(EditProjectsMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        amount_raw = request.POST.get("amount", "").strip()
        date_raw   = request.POST.get("approved_at", "").strip()
        note       = request.POST.get("note", "").strip()
        try:
            amount      = Decimal(amount_raw)
            approved_at = datetime.date.fromisoformat(date_raw)
            ProjectBudgetExtension.objects.create(
                project=project, amount=amount, approved_at=approved_at, note=note
            )
            messages.success(request, f"Budget-Erweiterung von {amount:,.0f} € hinzugefügt.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Ungültiger Betrag oder Datum.")
        return redirect("crm:project_detail", pk=pk)


class ProjectBudgetExtensionDeleteView(EditProjectsMixin, View):
    def post(self, request, pk, ext_pk):
        ext = get_object_or_404(ProjectBudgetExtension, pk=ext_pk, project_id=pk)
        ext.delete()
        messages.success(request, "Budget-Erweiterung entfernt.")
        return redirect("crm:project_detail", pk=pk)


# ---------------------------------------------------------------------------
# Kanban-Board
# ---------------------------------------------------------------------------

class KanbanView(CRMMixin, TemplateView):
    template_name = "crm/kanban.html"

    STATIC_COLS_BEFORE = []
    STATIC_COLS_AFTER = [
        {"status": "on_hold",  "label": "Pausiert", "team_lead": None, "employee_col": False,
         "hdr_bg": "bg-purple-50",  "hdr_border": "border-purple-200",
         "dot": "bg-purple-400",    "badge_bg": "bg-purple-100", "badge_text": "text-purple-700"},
        {"status": "invoiced", "label": "Rechnung", "team_lead": None, "employee_col": False,
         "hdr_bg": "bg-orange-50",  "hdr_border": "border-orange-200",
         "dot": "bg-orange-400",    "badge_bg": "bg-orange-100", "badge_text": "text-orange-700"},
    ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        projects = list(
            Project.objects
            .exclude(status__in=Project.ARCHIVED_STATUSES)
            .select_related("account", "team_lead")
            .prefetch_related("offers")
            .order_by("name")
        )

        # Set of project PKs that have at least one accepted offer (for badge)
        accepted_offer_pids = {
            p.pk for p in projects
            if any(o.status == "accepted" for o in p.offers.all())
        }

        # Static columns before active
        columns = []
        for col_def in self.STATIC_COLS_BEFORE:
            col_projects = [p for p in projects if p.status == col_def["status"]]
            columns.append({**col_def, "projects": col_projects, "count": len(col_projects)})

        # Dynamic employee columns — one per user with show_in_kanban=True
        from django.contrib.auth import get_user_model
        User = get_user_model()
        eligible_leads = list(
            User.objects.filter(show_in_kanban=True, is_active=True)
            .order_by("last_name", "first_name")
        )

        active_projects = [p for p in projects if p.status == "active"]
        active_by_lead = {}
        for p in active_projects:
            key = str(p.team_lead_id) if p.team_lead_id else "__none__"
            active_by_lead.setdefault(key, []).append(p)

        # Fixed "Beauftragt" column — active projects without team_lead (pool to claim)
        def _sorted_projects(proj_list):
            return sorted(proj_list, key=lambda p: p.name.lower()), [{"projects": sorted(proj_list, key=lambda p: p.name.lower())}]

        unassigned = active_by_lead.get("__none__", [])
        unassigned_sorted, unassigned_groups = _sorted_projects(unassigned)
        columns.append({
            "status": "active",
            "employee_col": True,
            "team_lead": None,
            "team_lead_id": "",
            "label": "Beauftragt",
            "projects": unassigned_sorted,
            "company_groups": unassigned_groups,
            "count": len(unassigned_sorted),
            "hdr_bg": "bg-teal-50",   "hdr_border": "border-teal-200",
            "dot": "bg-teal-500",     "badge_bg": "bg-teal-100", "badge_text": "text-teal-700",
        })

        all_leads_data = [(lead, active_by_lead.get(str(lead.pk), [])) for lead in eligible_leads]

        for lead, lead_projects in all_leads_data:
            sorted_projects, company_groups = _sorted_projects(lead_projects)

            columns.append({
                "status": "active",
                "employee_col": True,
                "team_lead": lead,
                "team_lead_id": str(lead.pk) if lead else "",
                "label": f"{lead.first_name} {lead.last_name}" if lead else "Nicht zugewiesen",
                "projects": sorted_projects,
                "company_groups": company_groups,
                "count": len(sorted_projects),
                "hdr_bg": "bg-green-50",   "hdr_border": "border-green-200",
                "dot": "bg-green-500",     "badge_bg": "bg-green-100", "badge_text": "text-green-700",
            })

        # Static columns after active
        for col_def in self.STATIC_COLS_AFTER:
            col_projects = [p for p in projects if p.status == col_def["status"]]
            columns.append({**col_def, "projects": col_projects, "count": len(col_projects)})

        ctx["columns"] = columns
        ctx["accepted_offer_pids"] = accepted_offer_pids
        return ctx


class ProjectKanbanMoveView(CRMMixin, View):
    """AJAX-Endpunkt: Projektstatus per Drag & Drop aktualisieren."""

    VALID_STATUSES = {s for s in Project.Status.values if s not in Project.ARCHIVED_STATUSES}

    def post(self, request):
        import json
        from apps.core.models import User
        try:
            data       = json.loads(request.body)
            project_id = data["project_id"]
            new_status = data["new_status"]
        except (KeyError, ValueError, json.JSONDecodeError):
            return JsonResponse({"ok": False, "error": "Invalid request"}, status=400)

        if new_status not in self.VALID_STATUSES:
            return JsonResponse({"ok": False, "error": "Invalid status"}, status=400)

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Not found"}, status=404)

        update_fields = ["status"]
        project.status = new_status

        # Update team_lead when dropping into an employee column
        if "team_lead_id" in data:
            tl_id = data["team_lead_id"]
            if tl_id:
                try:
                    project.team_lead = User.objects.get(pk=tl_id)
                except User.DoesNotExist:
                    pass
            else:
                project.team_lead = None
            update_fields.append("team_lead")

        project.save(update_fields=update_fields)
        return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Dokument-Upload / Viewer / Löschen
# ---------------------------------------------------------------------------

class DocumentUploadView(EditProjectsMixin, View):
    """PDF-Upload für ein Projekt-Dokument."""

    # Automatische Status-Übergänge beim Hochladen eines Dokuments
    STATUS_TRANSITIONS = {
        Document.DocumentType.OFFER:      ("lead",       "offer_sent"),
        Document.DocumentType.COMMISSION: ("offer_sent", "active"),
    }

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        doc_type = request.POST.get("document_type", "").strip()
        uploaded = request.FILES.get("file")

        if not uploaded or doc_type not in Document.DocumentType.values:
            messages.error(request, "Ungültiger Upload.")
            return redirect("crm:project_detail", pk=pk)

        title = request.POST.get("title", "").strip() or uploaded.name

        # Net amount for invoices (optional in generic upload)
        net_amount = None
        if doc_type == Document.DocumentType.INVOICE:
            raw = request.POST.get("net_amount", "").strip()
            if raw:
                try:
                    net_amount = Decimal(raw.replace(",", "."))
                except InvalidOperation:
                    pass

        doc = Document.objects.create(
            project=project,
            document_type=doc_type,
            title=title,
            file=uploaded,
            net_amount=net_amount,
            uploaded_by=request.user,
        )

        # Automatischer Status-Übergang
        transition = self.STATUS_TRANSITIONS.get(doc_type)
        if transition:
            from_status, to_status = transition
            if project.status == from_status:
                project.status = to_status
                project.save(update_fields=["status"])
                messages.success(
                    request,
                    f'Dokument gespeichert. Status geändert zu „{project.get_status_display()}".'
                )
            else:
                messages.success(request, "Dokument gespeichert.")
        else:
            messages.success(request, "Dokument gespeichert.")

        return redirect("crm:project_detail", pk=pk)


class ProjectInvoiceCreateView(EditInvoicesMixin, View):
    """
    Rechnung stellen: Erstellt ein Rechnungsdokument, trägt den Nettobetrag ein
    und setzt das Projekt auf 'Abgeschlossen'.

    Wenn ein Lexoffice API-Key für das Unternehmen des Projekts hinterlegt ist,
    wird die Rechnung direkt in Lexoffice erstellt und das PDF automatisch heruntergeladen.
    Andernfalls kann das PDF manuell hochgeladen werden.

    Nur erreichbar wenn project.status == 'invoiced'.
    """
    template_name = "crm/project_invoice_form.html"

    def _get_project(self, pk):
        return get_object_or_404(Project, pk=pk)

    @staticmethod
    def _lexoffice_configured(project) -> bool:
        return False

    def get(self, request, pk):
        project = self._get_project(pk)
        if project.status != Project.Status.INVOICED:
            messages.error(request, "Rechnung kann nur für Projekte im Status 'Rechnung' gestellt werden.")
            return redirect("crm:project_detail", pk=pk)
        return render(request, self.template_name, self._ctx(project))

    def post(self, request, pk):
        import datetime as _dt
        project = self._get_project(pk)
        if project.status != Project.Status.INVOICED:
            messages.error(request, "Ungültiger Status.")
            return redirect("crm:project_detail", pk=pk)

        use_lexoffice = self._lexoffice_configured(project)

        # ── Eingabe validieren ─────────────────────────────────────────────
        errors = {}
        title = request.POST.get("title", "").strip()
        if not title:
            errors["title"] = "Pflichtfeld."

        raw_amount = request.POST.get("net_amount", "").strip().replace(",", ".")
        net_amount = None
        try:
            net_amount = Decimal(raw_amount)
            if net_amount <= 0:
                errors["net_amount"] = "Betrag muss größer als 0 sein."
        except InvalidOperation:
            errors["net_amount"] = "Ungültiger Betrag."

        raw_date = request.POST.get("document_date", "").strip()
        document_date = None
        try:
            document_date = _dt.date.fromisoformat(raw_date)
        except ValueError:
            errors["document_date"] = "Ungültiges Datum."

        uploaded = request.FILES.get("file")
        if not use_lexoffice and not uploaded:
            errors["file"] = "Bitte PDF hochladen."

        payment_term_days = 30
        try:
            payment_term_days = int(request.POST.get("payment_term_days", 30))
        except ValueError:
            pass

        if errors:
            return render(request, self.template_name, {
                **self._ctx(project),
                "errors": errors,
                "post": request.POST,
            })

        # ── Lexoffice-Anbindung ────────────────────────────────────────────
        lexoffice_invoice_id = ""
        lexoffice_doc_number = request.POST.get("lexoffice_document_number", "").strip()
        pdf_content = None

        if use_lexoffice:
            from apps.core.lexoffice import LexofficeError, get_client_for_company
            try:
                client = get_client_for_company(project.company)
                lexoffice_invoice_id, lexoffice_doc_number = client.create_invoice(
                    customer_name=project.account.name if project.account else title,
                    line_description=title,
                    net_amount=net_amount,
                    invoice_date=document_date,
                    customer_lexoffice_id=(
                        project.account.lexoffice_id
                        if project.account and project.account.lexoffice_id else None
                    ),
                    payment_term_days=payment_term_days,
                )
                pdf_content = client.get_invoice_pdf(lexoffice_invoice_id)
            except LexofficeError as exc:
                logger.error("Lexoffice Fehler für Projekt %s: %s", project.pk, exc)
                return render(request, self.template_name, {
                    **self._ctx(project),
                    "lexoffice_error": str(exc),
                    "post": request.POST,
                })

        # ── Dokument speichern ─────────────────────────────────────────────
        from django.core.files.base import ContentFile

        doc_kwargs = dict(
            project=project,
            document_type=Document.DocumentType.INVOICE,
            title=title,
            net_amount=net_amount,
            gross_amount=net_amount * Decimal("1.19"),
            document_date=document_date,
            lexoffice_id=lexoffice_invoice_id,
            lexoffice_document_number=lexoffice_doc_number,
            uploaded_by=request.user,
        )

        if pdf_content:
            safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)
            doc_kwargs["file"] = ContentFile(pdf_content, name=f"{safe_title}.pdf")
        elif uploaded:
            doc_kwargs["file"] = uploaded

        Document.objects.create(**doc_kwargs)

        # ── Projektstatus ──────────────────────────────────────────────────
        project.status = Project.Status.COMPLETED
        project.save(update_fields=["status"])

        if use_lexoffice and lexoffice_doc_number:
            msg = f'Rechnung {lexoffice_doc_number} in Lexoffice erstellt und gespeichert. Projekt abgeschlossen.'
        else:
            msg = f'Rechnung „{title}" gespeichert. Projekt wurde auf „Abgeschlossen" gesetzt.'
        messages.success(request, msg)
        return redirect("crm:project_detail", pk=pk)

    @staticmethod
    def _ctx(project):
        import datetime as _dt
        return {
            "project": project,
            "today": _dt.date.today().isoformat(),
            "page_title": f"Rechnung stellen — {project.name}",
            "use_lexoffice": False,
        }


class DocumentDeleteView(EditProjectsMixin, View):
    """Löscht ein Dokument und seine Datei."""

    def post(self, request, pk, doc_pk):
        doc = get_object_or_404(Document, pk=doc_pk, project_id=pk)
        if doc.file:
            doc.file.delete(save=False)
        doc.delete()
        messages.success(request, "Dokument gelöscht.")
        return redirect("crm:project_detail", pk=pk)


class DocumentServeView(CRMMixin, View):
    """Sendet eine Dokument-Datei als Inline-PDF oder Download."""

    def get(self, request, pk, doc_pk):
        doc = get_object_or_404(Document, pk=doc_pk, project_id=pk)
        if not doc.file:
            from django.http import Http404
            raise Http404
        download = request.GET.get("download") == "1"
        disposition = "attachment" if download else "inline"
        response = HttpResponse(doc.file, content_type="application/pdf")
        filename = doc.file.name.split("/")[-1]
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Aktivitäten-Timeline (POST-only)
# ---------------------------------------------------------------------------

class ProjectActivityCreateView(LoginRequiredMixin, View):
    """Legt eine neue Projektaktivität an (POST-only)."""

    login_url = "/auth/login/"

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)

        activity_type = request.POST.get("activity_type", "").strip()
        title         = request.POST.get("title", "").strip()
        body          = request.POST.get("body", "").strip()
        occurred_at   = request.POST.get("occurred_at", "").strip()
        attachment    = request.FILES.get("attachment")

        if not title or activity_type not in ProjectActivity.ActivityType.values:
            messages.error(request, "Ungültige Eingabe. Typ und Titel sind Pflichtfelder.")
            return redirect("crm:project_detail", pk=pk)

        import datetime as _dt
        try:
            occurred_at_dt = _dt.datetime.fromisoformat(occurred_at) if occurred_at else _dt.datetime.now()
        except ValueError:
            occurred_at_dt = _dt.datetime.now()

        activity = ProjectActivity(
            project=project,
            activity_type=activity_type,
            title=title,
            body=body,
            occurred_at=occurred_at_dt,
            created_by=request.user,
        )
        if attachment:
            activity.attachment = attachment
        activity.save()

        messages.success(request, f'Aktivität „{title}" wurde gespeichert.')
        return redirect("crm:project_detail", pk=pk)


class ProjectActivityDeleteView(LoginRequiredMixin, View):
    """Löscht eine Projektaktivität — nur für Ersteller oder Staff."""

    login_url = "/auth/login/"

    def post(self, request, pk, act_pk):
        activity = get_object_or_404(ProjectActivity, pk=act_pk, project_id=pk)
        if activity.created_by != request.user and not request.user.is_staff:
            messages.error(request, "Keine Berechtigung zum Löschen dieser Aktivität.")
            return redirect("crm:project_detail", pk=pk)
        if activity.attachment:
            activity.attachment.delete(save=False)
        activity.delete()
        messages.success(request, "Aktivität gelöscht.")
        return redirect("crm:project_detail", pk=pk)


# ---------------------------------------------------------------------------
# vCard-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _vcard_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _contact_to_vcard(contact: Contact) -> str:
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{_vcard_escape(contact.last_name)};{_vcard_escape(contact.first_name)};;;",
        f"FN:{_vcard_escape(contact.get_full_name())}",
    ]
    if contact.company_name:
        lines.append(f"ORG:{_vcard_escape(contact.company_name)}")
    if contact.email:
        lines.append(f"EMAIL;TYPE=INTERNET:{_vcard_escape(contact.email)}")
    if contact.phone:
        lines.append(f"TEL;TYPE=WORK:{_vcard_escape(contact.phone)}")
    if contact.mobile:
        lines.append(f"TEL;TYPE=CELL:{_vcard_escape(contact.mobile)}")
    addr_parts = [
        "", "",
        contact.address_line1,
        contact.city, "",
        contact.postal_code,
        contact.country,
    ]
    if any(addr_parts):
        lines.append("ADR;TYPE=WORK:" + ";".join(_vcard_escape(p) for p in addr_parts))
    if contact.notes:
        lines.append(f"NOTE:{_vcard_escape(contact.notes)}")
    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def _parse_vcard(text: str) -> list[dict]:
    """Parst einen vCard-Text (3.0/4.0) und gibt eine Liste von Dicts zurück."""
    contacts = []
    current: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper() == "BEGIN:VCARD":
            current = {}
            continue
        if line.upper() == "END:VCARD":
            if current is not None:
                contacts.append(current)
            current = None
            continue
        if current is None:
            continue

        if ":" not in line:
            continue
        prop, _, value = line.partition(":")
        prop_name = prop.split(";")[0].upper()
        value = value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")

        if prop_name == "N":
            parts = value.split(";")
            current["last_name"]  = parts[0] if len(parts) > 0 else ""
            current["first_name"] = parts[1] if len(parts) > 1 else ""
        elif prop_name == "FN" and "first_name" not in current:
            parts = value.split(" ", 1)
            current["first_name"] = parts[0]
            current["last_name"]  = parts[1] if len(parts) > 1 else ""
        elif prop_name == "ORG":
            current["company_name"] = value.split(";")[0]
        elif prop_name == "EMAIL":
            current.setdefault("email", value)
        elif prop_name == "TEL":
            prop_upper = prop.upper()
            if "CELL" in prop_upper or "MOBILE" in prop_upper:
                current.setdefault("mobile", value)
            else:
                current.setdefault("phone", value)
        elif prop_name == "ADR":
            parts = value.split(";")
            current["address_line1"] = parts[2] if len(parts) > 2 else ""
            current["city"]          = parts[3] if len(parts) > 3 else ""
            current["postal_code"]   = parts[5] if len(parts) > 5 else ""
            current["country"]       = parts[6] if len(parts) > 6 else ""
        elif prop_name == "NOTE":
            current["notes"] = value

    return contacts


# ---------------------------------------------------------------------------
# Kontakt-Views
# ---------------------------------------------------------------------------

class ContactListView(CRMMixin, ListView):
    model               = Contact
    template_name       = "crm/contact_list.html"
    context_object_name = "contacts"
    paginate_by         = 50

    def get_queryset(self):
        qs = Contact.objects.prefetch_related("projects")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(company_name__icontains=q) |
                Q(email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        return ctx


class ContactDetailView(CRMMixin, DetailView):
    model         = Contact
    template_name = "crm/contact_detail.html"


class ContactCreateView(CRMMixin, CreateView):
    model         = Contact
    form_class    = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        contact = form.save()
        messages.success(self.request, f'Kontakt „{contact}" wurde erstellt.')
        return redirect("crm:contact_detail", pk=contact.pk)

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]          = "Neuer Kontakt"
        ctx["submit_label"]        = "Kontakt erstellen"
        ctx["google_maps_api_key"] = dj_settings.GOOGLE_MAPS_API_KEY
        return ctx


class ContactUpdateView(CRMMixin, UpdateView):
    model         = Contact
    form_class    = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        contact = form.save()
        messages.success(self.request, f'Kontakt „{contact}" wurde aktualisiert.')
        return redirect("crm:contact_detail", pk=contact.pk)

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]          = f"{self.object} bearbeiten"
        ctx["submit_label"]        = "Speichern"
        ctx["google_maps_api_key"] = dj_settings.GOOGLE_MAPS_API_KEY
        return ctx


class ContactVCardExportView(CRMMixin, View):
    def get(self, request, pk):
        contact = get_object_or_404(Contact, pk=pk)
        vcf = _contact_to_vcard(contact)
        filename = f"{contact.last_name}_{contact.first_name}.vcf".replace(" ", "_")
        response = HttpResponse(vcf, content_type="text/vcard; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ContactVCardImportView(CRMMixin, View):
    def post(self, request):
        vcf_file = request.FILES.get("vcf_file")
        if not vcf_file:
            messages.error(request, "Keine Datei ausgewählt.")
            return redirect("crm:contact_list")

        text = vcf_file.read().decode("utf-8", errors="replace")
        parsed = _parse_vcard(text)
        created = 0
        for data in parsed:
            first = data.get("first_name", "").strip()
            last  = data.get("last_name", "").strip()
            if not first and not last:
                continue
            Contact.objects.create(
                first_name   = first,
                last_name    = last,
                company_name = data.get("company_name", ""),
                email        = data.get("email", ""),
                phone        = data.get("phone", ""),
                mobile       = data.get("mobile", ""),
                address_line1= data.get("address_line1", ""),
                postal_code  = data.get("postal_code", ""),
                city         = data.get("city", ""),
                country      = data.get("country", "") or "Deutschland",
                notes        = data.get("notes", ""),
            )
            created += 1

        messages.success(request, f"{created} Kontakt(e) importiert.")
        return redirect("crm:contact_list")


# ---------------------------------------------------------------------------
# Offer Views
# ---------------------------------------------------------------------------

def _build_offer_formset(request, offer=None, extra=1):
    """Gibt ein OfferItemFormSet zurück — mit konfigurierbarem extra-Wert."""
    from django.forms import inlineformset_factory
    from .forms import OfferItemForm
    FS = inlineformset_factory(
        Offer, OfferItem, form=OfferItemForm,
        extra=extra, can_delete=True,
    )
    if request.method == "POST":
        return FS(request.POST, instance=offer)
    return FS(instance=offer)


class OfferListView(CRMMixin, ListView):
    model               = Offer
    template_name       = "crm/offer_list.html"
    context_object_name = "offers"
    paginate_by         = 30

    def get_queryset(self):
        qs = Offer.objects.select_related("project", "created_by").order_by("-offer_date", "-created_at")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(offer_number__icontains=q) |
                Q(title__icontains=q) |
                Q(project__name__icontains=q)
            )
        status = self.request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]              = self.request.GET.get("q", "")
        ctx["status_filter"]  = self.request.GET.get("status", "")
        ctx["status_choices"] = Offer.Status.choices
        return ctx


def _set_recipient_account(offer, request):
    """Reads recipient_account UUID from POST and links it to the offer."""
    account_id = request.POST.get("recipient_account", "").strip()
    if account_id:
        try:
            offer.recipient_account = Account.objects.get(pk=account_id)
        except (Account.DoesNotExist, Exception):
            offer.recipient_account = None
    else:
        offer.recipient_account = None


def _account_address(acc) -> str:
    """Build a multi-line address string from an Account's address fields."""
    parts = []
    if acc.address_line1:
        parts.append(acc.address_line1)
    if acc.address_line2:
        parts.append(acc.address_line2)
    city_line = " ".join(filter(None, [acc.postal_code, acc.city]))
    if city_line:
        parts.append(city_line)
    if acc.country and acc.country != "Deutschland":
        parts.append(acc.country)
    return "\n".join(parts)


def _textblock_defaults(scope: str) -> dict:
    """Return initial field values from is_default TextBlocks for the given scope (offer/invoice)."""
    payment_field = "payment_info" if scope == "invoice" else "payment_terms"
    mapping = {"intro": "intro_text", "closing": "closing_text", "payment": payment_field}
    initial = {}
    qs = TextBlock.objects.filter(is_default=True, scope__in=[scope, "both"])
    for tb in qs:
        field = mapping.get(tb.category)
        if field and field not in initial:
            initial[field] = tb.content
    return initial


class OfferCreateView(EditOffersMixin, View):
    template_name = "crm/offer_form.html"

    def _get_project(self, pk):
        return get_object_or_404(Project, pk=pk)

    def get(self, request, pk):
        project = self._get_project(pk)
        initial = {**_textblock_defaults("offer")}
        # Pre-fill from GET params (e.g. from LeadInquiryImportView)
        for field in ["recipient_name", "recipient_email", "recipient_address"]:
            if request.GET.get(field):
                initial[field] = request.GET[field]
        # Pre-fill description into intro_text (overrides textblock default)
        if request.GET.get("description"):
            initial["intro_text"] = request.GET["description"]
        # Also try from account if not pre-filled
        if project.account and not initial.get("recipient_name"):
            acc = project.account
            initial["recipient_name"]    = acc.name
            initial["recipient_email"]   = acc.billing_email or acc.email
            initial["recipient_address"] = _account_address(acc)
        # Widerrufsbelehrung: bei Privatpersonen standardmäßig anhaken
        if project.account:
            from apps.crm.models import Account
            is_private = project.account.account_type == Account.AccountType.PRIVATE
            initial.setdefault("include_widerrufsbelehrung", is_private)
        # Lead-Import: customer_type aus GET-Param auswerten (überschreibt Account-Default)
        if request.GET.get("customer_type") == "private":
            initial["include_widerrufsbelehrung"] = True
        elif request.GET.get("customer_type") == "company":
            initial["include_widerrufsbelehrung"] = False
        from django.conf import settings as dj_settings
        form    = OfferForm(initial=initial)
        formset = _build_offer_formset(request, extra=3)
        return render(request, self.template_name, {
            "form":               form,
            "formset":            formset,
            "project":            project,
            "page_title":         "Neues Angebot",
            "from_inquiry":       bool(request.GET.get("recipient_name")),
            "google_maps_api_key": dj_settings.GOOGLE_MAPS_API_KEY,
        })

    def post(self, request, pk):
        project = self._get_project(pk)
        form    = OfferForm(request.POST)
        formset = _build_offer_formset(request, extra=3)

        if form.is_valid() and formset.is_valid():
            offer = form.save(commit=False)
            offer.project    = project
            offer.created_by = request.user
            _set_recipient_account(offer, request)
            offer.save()
            formset.instance = offer
            formset.save()
            return redirect("crm:offer_preview", pk=offer.pk)

        return render(request, self.template_name, {
            "form":    form,
            "formset": formset,
            "project": project,
            "page_title": "Neues Angebot",
        })

    # AdminOrLeadMixin needs test_func — inherited via mixin chain
    # but View doesn't call setup automatically for test_func, so we expose
    # get_test_func via UserPassesTestMixin which calls test_func on dispatch.


class OfferCreateStandaloneView(EditOffersMixin, View):
    """Angebot direkt aus der Angebotsliste erstellen — ohne Projekt-PK in der URL."""
    template_name = "crm/offer_form.html"

    def get(self, request):
        form    = OfferForm(initial={**_textblock_defaults("offer")})
        formset = _build_offer_formset(request, extra=3)
        return render(request, self.template_name, {
            "form": form, "formset": formset, "project": None,
            "page_title": "Neues Angebot",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })

    def post(self, request):
        form    = OfferForm(request.POST)
        formset = _build_offer_formset(request, extra=3)
        if form.is_valid() and formset.is_valid():
            offer            = form.save(commit=False)
            offer.project    = form.cleaned_data.get("project")
            offer.created_by = request.user
            _set_recipient_account(offer, request)
            offer.save()
            formset.instance = offer
            formset.save()
            return redirect("crm:offer_preview", pk=offer.pk)
        return render(request, self.template_name, {
            "form": form, "formset": formset, "project": None,
            "page_title": "Neues Angebot",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })


class OfferDetailView(LoginRequiredMixin, DetailView):
    login_url     = "/auth/login/"
    model         = Offer
    template_name = "crm/offer_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        offer = self.object
        items = list(offer.items.all())
        ctx["items"]       = items
        ctx["net_total"]   = offer.net_total
        ctx["tax_amount"]  = offer.tax_amount
        ctx["gross_total"] = offer.gross_total
        return ctx


class OfferUpdateView(EditOffersMixin, View):
    template_name = "crm/offer_form.html"

    def _get_offer(self, pk):
        return get_object_or_404(Offer, pk=pk)

    def get(self, request, pk):
        offer   = self._get_offer(pk)
        form    = OfferForm(instance=offer)
        formset = _build_offer_formset(request, offer=offer, extra=1)
        return render(request, self.template_name, {
            "form":    form,
            "formset": formset,
            "project": offer.project,
            "offer":   offer,
            "page_title": f"Angebot {offer.offer_number} bearbeiten",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })

    def post(self, request, pk):
        offer   = self._get_offer(pk)
        form    = OfferForm(request.POST, instance=offer)
        formset = _build_offer_formset(request, offer=offer, extra=1)

        if form.is_valid() and formset.is_valid():
            updated = form.save(commit=False)
            _set_recipient_account(updated, request)
            updated.save()
            formset.save()
            return redirect("crm:offer_preview", pk=offer.pk)

        return render(request, self.template_name, {
            "form":    form,
            "formset": formset,
            "project": offer.project,
            "offer":   offer,
            "page_title": f"Angebot {offer.offer_number} bearbeiten",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })


class OfferPreviewView(LoginRequiredMixin, View):
    """Browser-Vorschau eines Angebots — sieht aus wie das PDF, mit Aktionsleiste oben."""
    login_url = "/auth/login/"

    def get(self, request, pk):
        from decimal import Decimal
        offer   = get_object_or_404(Offer, pk=pk)
        items   = list(offer.items.all())
        subtotal = sum((i.net_amount for i in items), Decimal("0.00"))
        return render(request, "crm/offer_preview.html", {
            "offer":           offer,
            "items":           items,
            "subtotal":        subtotal,
            "discount_amount": offer.discount_amount,
            "net_total":       offer.net_total,
            "tax_amount":      offer.tax_amount,
            "gross_total":     offer.gross_total,
            "show_signature_block": True,
            **_company_ctx(),
        })


class OfferPDFView(LoginRequiredMixin, View):
    login_url = "/auth/login/"

    def get(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        try:
            import weasyprint
        except ImportError:
            return HttpResponse(
                "WeasyPrint ist nicht installiert. Bitte 'pip install weasyprint' ausführen.",
                status=503,
                content_type="text/plain; charset=utf-8",
            )

        items    = list(offer.items.all())
        subtotal = sum((i.net_amount for i in items), __import__('decimal').Decimal("0.00"))
        show_sig = offer.status in (Offer.Status.DRAFT, Offer.Status.SENT) and not offer.is_order_confirmation
        from django.template.loader import render_to_string
        html_string = render_to_string("crm/offer_pdf.html", {
            "offer":           offer,
            "items":           items,
            "subtotal":        subtotal,
            "discount_amount": offer.discount_amount,
            "net_total":       offer.net_total,
            "tax_amount":      offer.tax_amount,
            "gross_total":     offer.gross_total,
            "show_signature_block": show_sig,
            **_company_ctx(),
        }, request=request)

        pdf = weasyprint.HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{offer.offer_number}.pdf"'
        return response


def _generate_offer_pdf_bytes(offer, request=None, show_signature_block=False):
    """Shared helper: renders offer PDF and returns bytes. Raises ImportError if WeasyPrint missing."""
    import weasyprint
    from decimal import Decimal
    from django.template.loader import render_to_string
    items    = list(offer.items.all())
    subtotal = sum((i.net_amount for i in items), Decimal("0.00"))
    html_string = render_to_string("crm/offer_pdf.html", {
        "offer":           offer,
        "items":           items,
        "subtotal":        subtotal,
        "discount_amount": offer.discount_amount,
        "net_total":       offer.net_total,
        "tax_amount":      offer.tax_amount,
        "gross_total":     offer.gross_total,
        "show_signature_block": show_signature_block,
        **_company_ctx(),
    })
    base_url = request.build_absolute_uri("/") if request else "/"
    return weasyprint.HTML(string=html_string, base_url=base_url).write_pdf()


class OfferSendView(SendOffersMixin, View):
    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)

        if not offer.recipient_email:
            messages.error(request, "Kein Empfänger hinterlegt.")
            return redirect("crm:offer_detail", pk=offer.pk)

        try:
            pdf_bytes = _generate_offer_pdf_bytes(offer, request, show_signature_block=True)
        except ImportError:
            messages.error(request, "WeasyPrint ist nicht installiert — PDF-Versand nicht möglich.")
            return redirect("crm:offer_detail", pk=offer.pk)

        commission_url = request.build_absolute_uri(
            reverse("crm:offer_commission_confirm", kwargs={"token": offer.commission_token})
        )
        msg = _build_email(
            subject=f"Angebot {offer.offer_number} – {offer.project.name if offer.project else offer.title}",
            text_body=(
                f"Sehr geehrte/r {offer.recipient_name or 'Damen und Herren'},\n\n"
                f"anbei finden Sie unser Angebot {offer.offer_number}.\n\n"
                f"Sie können das Angebot bequem online bestätigen:\n{commission_url}\n\n"
                f"Alternativ können Sie das beigefügte PDF unterschreiben, "
                f"mit Ort, Datum und Unterschrift versehen und an uns zurücksenden.\n\n"
                f"Mit freundlichen Grüßen"
            ),
            to=[offer.recipient_email],
        )
        msg.attach(f"{offer.offer_number}.pdf", pdf_bytes, "application/pdf")
        msg.send()

        offer.status = Offer.Status.SENT
        offer.save(update_fields=["status"])

        # PDF-Snapshot als Dokument am Projekt archivieren
        if offer.project:
            from django.core.files.base import ContentFile
            doc = Document(
                project=offer.project,
                document_type=Document.DocumentType.OFFER,
                title=f"{offer.offer_number} – {offer.title}",
            )
            doc.file.save(f"{offer.offer_number}.pdf", ContentFile(pdf_bytes), save=True)

        messages.success(request, f"Angebot {offer.offer_number} wurde an {offer.recipient_email} versendet.")
        return redirect("crm:offer_detail", pk=offer.pk)


class OfferStatusUpdateView(EditOffersMixin, View):
    ALLOWED_TRANSITIONS = {
        Offer.Status.DRAFT:    {Offer.Status.SENT},
        Offer.Status.SENT:     {Offer.Status.ACCEPTED, Offer.Status.REJECTED},
    }

    def post(self, request, pk):
        offer      = get_object_or_404(Offer, pk=pk)
        new_status = request.POST.get("status", "")
        allowed    = self.ALLOWED_TRANSITIONS.get(offer.status, set())

        if new_status not in {s.value for s in allowed}:
            messages.error(request, "Ungültiger Statuswechsel.")
            return redirect("crm:offer_detail", pk=offer.pk)

        offer.status = new_status
        offer.save(update_fields=["status"])
        if new_status == Offer.Status.ACCEPTED and offer.project:
            offer.project.status = Project.Status.ACTIVE
            offer.project.save(update_fields=["status"])
        label = dict(Offer.Status.choices).get(new_status, new_status)
        messages.success(request, f'Status auf "{label}" gesetzt.')
        return redirect("crm:offer_detail", pk=offer.pk)


class OfferDeleteView(DeleteOffersMixin, View):
    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        if offer.status != Offer.Status.DRAFT:
            messages.error(request, "Nur Angebote im Entwurfsstatus können gelöscht werden.")
            return redirect("crm:offer_detail", pk=offer.pk)
        project_pk = offer.project.pk if offer.project else None
        number = offer.offer_number
        offer.delete()
        messages.success(request, f"Angebot {number} wurde gelöscht.")
        if project_pk:
            return redirect("crm:project_detail", pk=project_pk)
        return redirect("crm:offer_list")


# ---------------------------------------------------------------------------
# Invoice Views
# ---------------------------------------------------------------------------

def _build_invoice_formset(request, invoice=None, extra=1):
    FormSet = forms.inlineformset_factory(
        Invoice, InvoiceItem, form=InvoiceItemForm, extra=extra, can_delete=True
    )
    if request.method == "POST":
        return FormSet(request.POST, instance=invoice)
    return FormSet(instance=invoice)


def _generate_invoice_pdf_bytes(invoice, request):
    """Generate PDF bytes for an invoice using WeasyPrint."""
    html_string = render_to_string(
        "crm/invoice_pdf.html",
        {"invoice": invoice, "items": invoice.items.all(), **_company_ctx()},
        request=request,
    )
    from weasyprint import HTML
    return HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()


def _build_zugferd_xml(invoice, cs, items) -> str:
    """Build ZUGFeRD EN 16931 XML string."""
    from decimal import Decimal
    from xml.sax.saxutils import escape

    UNIT_CODE_MAP = {
        "stunden": "HUR", "std": "HUR", "h": "HUR",
        "tage": "DAY", "tag": "DAY",
        "stück": "C62", "stk": "C62", "pcs": "C62",
        "pauschal": "C62", "ls": "C62",
    }

    def uc(unit_str: str) -> str:
        return UNIT_CODE_MAP.get((unit_str or "").lower().strip(), "C62")

    def fmt(d) -> str:
        return f"{Decimal(str(d)):.2f}"

    def x(s) -> str:
        return escape(str(s or ""))

    lines_xml = ""
    for item in items:
        lines_xml += f"""
    <ram:IncludedSupplyChainTradeLineItem>
      <ram:AssociatedDocumentLineDocument>
        <ram:LineID>{item.position}</ram:LineID>
      </ram:AssociatedDocumentLineDocument>
      <ram:SpecifiedTradeProduct>
        <ram:Name>{x(item.description)}</ram:Name>
      </ram:SpecifiedTradeProduct>
      <ram:SpecifiedLineTradeAgreement>
        <ram:NetPriceProductTradePrice>
          <ram:ChargeAmount>{fmt(item.unit_price)}</ram:ChargeAmount>
        </ram:NetPriceProductTradePrice>
      </ram:SpecifiedLineTradeAgreement>
      <ram:SpecifiedLineTradeDelivery>
        <ram:BilledQuantity unitCode="{uc(item.unit)}">{fmt(item.quantity)}</ram:BilledQuantity>
      </ram:SpecifiedLineTradeDelivery>
      <ram:SpecifiedLineTradeSettlement>
        <ram:ApplicableTradeTax>
          <ram:TypeCode>VAT</ram:TypeCode>
          <ram:CategoryCode>S</ram:CategoryCode>
          <ram:RateApplicablePercent>{fmt(invoice.tax_rate)}</ram:RateApplicablePercent>
        </ram:ApplicableTradeTax>
        <ram:SpecifiedTradeSettlementLineMonetarySummation>
          <ram:LineTotalAmount>{fmt(item.net_amount)}</ram:LineTotalAmount>
        </ram:SpecifiedTradeSettlementLineMonetarySummation>
      </ram:SpecifiedLineTradeSettlement>
    </ram:IncludedSupplyChainTradeLineItem>"""

    due_date_xml = ""
    if invoice.due_date:
        due_date_xml = f"""
      <ram:SpecifiedTradePaymentTerms>
        <ram:DueDateDateTime>
          <udt:DateTimeString format="102">{invoice.due_date.strftime('%Y%m%d')}</udt:DateTimeString>
        </ram:DueDateDateTime>
      </ram:SpecifiedTradePaymentTerms>"""

    vat_id_xml = ""
    if cs.vat_id:
        vat_id_xml = f"""
        <ram:SpecifiedTaxRegistration>
          <ram:ID schemeID="VA">{x(cs.vat_id)}</ram:ID>
        </ram:SpecifiedTaxRegistration>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
  xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
  xmlns:qdt="urn:un:unece:uncefact:data:standard:QualifiedDataType:100"
  xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
  <rsm:ExchangedDocumentContext>
    <ram:GuidelineSpecifiedDocumentContextParameter>
      <ram:ID>urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:en16931</ram:ID>
    </ram:GuidelineSpecifiedDocumentContextParameter>
  </rsm:ExchangedDocumentContext>
  <rsm:ExchangedDocument>
    <ram:ID>{x(invoice.invoice_number)}</ram:ID>
    <ram:TypeCode>380</ram:TypeCode>
    <ram:IssueDateTime>
      <udt:DateTimeString format="102">{invoice.invoice_date.strftime('%Y%m%d')}</udt:DateTimeString>
    </ram:IssueDateTime>
  </rsm:ExchangedDocument>
  <rsm:SupplyChainTradeTransaction>
{lines_xml}
    <ram:ApplicableHeaderTradeAgreement>
      <ram:SellerTradeParty>
        <ram:Name>{x(cs.company_name)}</ram:Name>
        <ram:PostalTradeAddress>
          <ram:LineOne>{x(cs.street)}</ram:LineOne>
          <ram:PostcodeCode>{x(cs.postal_code)}</ram:PostcodeCode>
          <ram:CityName>{x(cs.city)}</ram:CityName>
          <ram:CountryID>DE</ram:CountryID>
        </ram:PostalTradeAddress>{vat_id_xml}
      </ram:SellerTradeParty>
      <ram:BuyerTradeParty>
        <ram:Name>{x(invoice.recipient_name)}</ram:Name>
        <ram:PostalTradeAddress>
          <ram:LineOne>{x(invoice.recipient_address)}</ram:LineOne>
          <ram:CountryID>DE</ram:CountryID>
        </ram:PostalTradeAddress>
      </ram:BuyerTradeParty>
    </ram:ApplicableHeaderTradeAgreement>
    <ram:ApplicableHeaderTradeDelivery/>
    <ram:ApplicableHeaderTradeSettlement>
      <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>{due_date_xml}
      <ram:ApplicableTradeTax>
        <ram:CalculatedAmount>{fmt(invoice.tax_amount)}</ram:CalculatedAmount>
        <ram:TypeCode>VAT</ram:TypeCode>
        <ram:BasisAmount>{fmt(invoice.net_total)}</ram:BasisAmount>
        <ram:CategoryCode>S</ram:CategoryCode>
        <ram:RateApplicablePercent>{fmt(invoice.tax_rate)}</ram:RateApplicablePercent>
      </ram:ApplicableTradeTax>
      <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
        <ram:LineTotalAmount>{fmt(invoice.net_total)}</ram:LineTotalAmount>
        <ram:TaxBasisTotalAmount>{fmt(invoice.net_total)}</ram:TaxBasisTotalAmount>
        <ram:TaxTotalAmount currencyID="EUR">{fmt(invoice.tax_amount)}</ram:TaxTotalAmount>
        <ram:GrandTotalAmount>{fmt(invoice.gross_total)}</ram:GrandTotalAmount>
        <ram:DuePayableAmount>{fmt(invoice.gross_total)}</ram:DuePayableAmount>
      </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    </ram:ApplicableHeaderTradeSettlement>
  </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""


def _generate_zugferd_invoice(invoice, request):
    """Generate ZUGFeRD PDF. Falls back to plain PDF if factur-x unavailable."""
    from apps.core.models import CompanySettings
    cs = CompanySettings.get()
    items = list(invoice.items.all())
    plain_pdf = _generate_invoice_pdf_bytes(invoice, request)
    try:
        xml_string = _build_zugferd_xml(invoice, cs, items)
    except Exception as e:
        logger.warning("ZUGFeRD XML build failed: %s", e)
        return plain_pdf, False
    try:
        from facturx import generate_from_binary
        import io
        output = io.BytesIO()
        generate_from_binary(
            plain_pdf,
            xml_string.encode("utf-8"),
            output_pdf_file=output,
        )
        return output.getvalue(), True
    except ImportError:
        logger.info("factur-x not installed — returning plain PDF")
        return plain_pdf, False
    except Exception as e:
        logger.warning("ZUGFeRD embedding failed: %s", e)
        return plain_pdf, False


class InvoiceListView(CRMMixin, ListView):
    model = Invoice
    template_name = "crm/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 25

    def get_queryset(self):
        qs = Invoice.objects.select_related("project", "offer").order_by("-invoice_date", "-created_at")
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        if q:
            qs = qs.filter(
                Q(invoice_number__icontains=q)
                | Q(title__icontains=q)
                | Q(project__name__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.request.GET.get("q", "")
        ctx["status_filter"] = self.request.GET.get("status", "")
        ctx["status_choices"] = Invoice.Status.choices
        ctx["today"] = date.today()
        return ctx


class InvoiceCreateView(EditInvoicesMixin, View):
    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        initial = {**_textblock_defaults("invoice"), "title": f"Rechnung – {project.name}"}
        if project.account:
            acc = project.account
            initial["recipient_name"]    = acc.name
            initial["recipient_email"]   = acc.billing_email or acc.email
            initial["recipient_address"] = _account_address(acc)
        form = InvoiceForm(initial=initial)
        formset = _build_invoice_formset(request, extra=3)
        return render(request, "crm/invoice_form.html", {
            "form": form, "formset": formset, "project": project, "offer": None,
            "page_title": "Neue Rechnung",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        form = InvoiceForm(request.POST)
        formset = _build_invoice_formset(request)
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.project = project
            invoice.created_by = request.user
            invoice.save()
            formset.instance = invoice
            formset.save()
            invoice.net_total_cached = invoice.net_total
            invoice.save(update_fields=["net_total_cached"])
            messages.success(request, f"Rechnung {invoice.invoice_number} erstellt.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        return render(request, "crm/invoice_form.html", {
            "form": form, "formset": formset, "project": project, "offer": None,
            "page_title": "Neue Rechnung",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })


class InvoiceCreateStandaloneView(EditInvoicesMixin, View):
    """Rechnung direkt aus der Rechnungsliste erstellen — ohne Projekt-PK in der URL."""

    def get(self, request):
        form    = InvoiceForm(initial=_textblock_defaults("invoice"))
        formset = _build_invoice_formset(request, extra=3)
        return render(request, "crm/invoice_form.html", {
            "form": form, "formset": formset, "project": None, "offer": None,
            "page_title": "Neue Rechnung",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })

    def post(self, request):
        form    = InvoiceForm(request.POST)
        formset = _build_invoice_formset(request)
        if form.is_valid() and formset.is_valid():
            invoice            = form.save(commit=False)
            invoice.project    = form.cleaned_data.get("project")
            invoice.created_by = request.user
            invoice.save()
            formset.instance = invoice
            formset.save()
            invoice.net_total_cached = invoice.net_total
            invoice.save(update_fields=["net_total_cached"])
            messages.success(request, f"Rechnung {invoice.invoice_number} erstellt.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        return render(request, "crm/invoice_form.html", {
            "form": form, "formset": formset, "project": None, "offer": None,
            "page_title": "Neue Rechnung",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })


class InvoiceFromOfferView(EditInvoicesMixin, View):
    """1-Klick: Rechnungsentwurf direkt aus Angebot anlegen, ohne Zwischenformular."""

    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        if offer.status != Offer.Status.ACCEPTED:
            messages.error(request, "Rechnungen können nur aus beauftragten Angeboten erstellt werden.")
            return redirect("crm:offer_detail", pk=offer.pk)

        invoice = Invoice.objects.create(
            project            = offer.project,
            offer              = offer,
            created_by         = request.user,
            title              = offer.title,
            recipient_name     = offer.recipient_name,
            recipient_email    = offer.recipient_email,
            recipient_address  = offer.recipient_address,
            tax_rate           = offer.tax_rate,
            intro_text         = offer.intro_text,
            closing_text       = offer.closing_text,
            payment_info       = offer.payment_terms,
            discount_percent   = offer.discount_percent,
            discount_amount_eur= offer.discount_amount_eur,
        )

        InvoiceItem.objects.bulk_create([
            InvoiceItem(
                invoice          = invoice,
                position         = item.position,
                item_type        = item.item_type,
                billing_type     = item.billing_type,
                title            = item.title,
                description      = item.description,
                quantity         = item.quantity,
                unit             = item.unit,
                unit_price       = item.unit_price,
                discount_percent = item.discount_percent,
            )
            for item in offer.items.all()
        ])

        invoice.net_total_cached = invoice.net_total
        invoice.save(update_fields=["net_total_cached"])

        messages.success(request, f"Rechnungsentwurf {invoice.invoice_number} aus Angebot übernommen.")
        return redirect("crm:invoice_detail", pk=invoice.pk)


class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = "crm/invoice_detail.html"
    login_url = "/auth/login/"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        invoice = self.object
        ctx["items"] = invoice.items.all()
        ctx["net_total"] = invoice.net_total
        ctx["tax_amount"] = invoice.tax_amount
        ctx["gross_total"] = invoice.gross_total
        ctx["today"] = date.today()
        return ctx


class InvoiceUpdateView(EditInvoicesMixin, View):
    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        if invoice.status != Invoice.Status.DRAFT:
            messages.error(request, "Nur Entwürfe können bearbeitet werden.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        form = InvoiceForm(instance=invoice)
        formset = _build_invoice_formset(request, invoice=invoice, extra=1)
        return render(request, "crm/invoice_form.html", {
            "form": form, "formset": formset, "project": invoice.project,
            "offer": invoice.offer, "invoice": invoice,
            "page_title": f"Rechnung {invoice.invoice_number} bearbeiten",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        if invoice.status != Invoice.Status.DRAFT:
            messages.error(request, "Nur Entwürfe können bearbeitet werden.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        form = InvoiceForm(request.POST, instance=invoice)
        formset = _build_invoice_formset(request, invoice=invoice)
        if form.is_valid() and formset.is_valid():
            invoice = form.save()
            formset.save()
            invoice.net_total_cached = invoice.net_total
            invoice.save(update_fields=["net_total_cached"])
            messages.success(request, "Rechnung gespeichert.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        return render(request, "crm/invoice_form.html", {
            "form": form, "formset": formset, "project": invoice.project,
            "offer": invoice.offer, "invoice": invoice,
            "page_title": f"Rechnung {invoice.invoice_number} bearbeiten",
            "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
        })


class InvoicePDFView(LoginRequiredMixin, View):
    login_url = "/auth/login/"

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        try:
            pdf_bytes, is_zugferd = _generate_zugferd_invoice(invoice, request)
        except ImportError:
            messages.error(request, "WeasyPrint ist nicht installiert.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
        return response


class InvoiceSendView(SendInvoicesMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        if not invoice.recipient_email:
            messages.error(request, "Kein Empfänger hinterlegt.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        try:
            pdf_bytes, is_zugferd = _generate_zugferd_invoice(invoice, request)
        except Exception as e:
            messages.error(request, f"PDF-Generierung fehlgeschlagen: {e}")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        subject_suffix = f" – {invoice.project.name}" if invoice.project else ""
        email = _build_email(
            subject=f"Rechnung {invoice.invoice_number}{subject_suffix}",
            text_body=(
                f"Sehr geehrte/r {invoice.recipient_name or 'Damen und Herren'},\n\n"
                + (invoice.intro_text or f"anbei erhalten Sie Ihre Rechnung {invoice.invoice_number}.")
                + "\n\nMit freundlichen Grüßen"
            ),
            to=[invoice.recipient_email],
        )
        email.attach(f"{invoice.invoice_number}.pdf", pdf_bytes, "application/pdf")
        email.send()
        invoice.status = Invoice.Status.SENT
        invoice.save(update_fields=["status"])

        # PDF-Snapshot als Dokument am Projekt archivieren
        if invoice.project:
            from django.core.files.base import ContentFile
            inv_doc = Document(
                project=invoice.project,
                document_type=Document.DocumentType.INVOICE,
                title=f"{invoice.invoice_number} – {invoice.title}",
            )
            inv_doc.file.save(f"{invoice.invoice_number}.pdf", ContentFile(pdf_bytes), save=True)
            project = invoice.project
            if project.status not in {Project.Status.INVOICED, Project.Status.COMPLETED}:
                project.status = Project.Status.INVOICED
                project.save(update_fields=["status"])
        messages.success(request, f"Rechnung an {invoice.recipient_email} versendet.")
        return redirect("crm:invoice_detail", pk=invoice.pk)


class InvoiceStatusUpdateView(EditInvoicesMixin, View):
    ALLOWED_TRANSITIONS = {
        Invoice.Status.DRAFT:  {Invoice.Status.SENT, Invoice.Status.CANCELLED},
        Invoice.Status.SENT:   {Invoice.Status.PAID, Invoice.Status.CANCELLED},
    }

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        new_status = request.POST.get("status")
        allowed = self.ALLOWED_TRANSITIONS.get(invoice.status, set())
        if new_status not in allowed:
            messages.error(request, "Ungültiger Statuswechsel.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        invoice.status = new_status
        if new_status == Invoice.Status.PAID:
            invoice.payment_date = date.today()
            if invoice.project:
                invoice.project.status = Project.Status.COMPLETED
                invoice.project.save(update_fields=["status"])
        invoice.save()
        messages.success(request, f"Status auf '{invoice.get_status_display()}' gesetzt.")
        return redirect("crm:invoice_detail", pk=invoice.pk)


class InvoiceDeleteView(DeleteInvoicesMixin, View):
    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        if invoice.status != Invoice.Status.DRAFT:
            messages.error(request, "Nur Entwürfe können gelöscht werden.")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        project_pk = invoice.project_id
        invoice.delete()
        messages.success(request, "Rechnung gelöscht.")
        if project_pk:
            return redirect("crm:project_detail", pk=project_pk)
        return redirect("crm:invoice_list")


class InvoiceXRechnungView(LoginRequiredMixin, View):
    login_url = "/auth/login/"

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        from apps.core.models import CompanySettings
        cs = CompanySettings.get()
        items = list(invoice.items.all())
        try:
            xml_string = _build_zugferd_xml(invoice, cs, items)
        except Exception as e:
            messages.error(request, f"XML-Generierung fehlgeschlagen: {e}")
            return redirect("crm:invoice_detail", pk=invoice.pk)
        response = HttpResponse(xml_string, content_type="application/xml; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{invoice.invoice_number}_xrechnung.xml"'
        return response


class OfferOrderConfirmationView(SendOffersMixin, View):
    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        offer.is_order_confirmation = True
        offer.save(update_fields=["is_order_confirmation"])
        return redirect("crm:offer_pdf", pk=offer.pk)


class OfferPublicConfirmView(View):
    """Public: Kunde bestätigt Angebot online (kein Login nötig)."""

    def _get_offer(self, token):
        return get_object_or_404(Offer, commission_token=token)

    def get(self, request, token):
        offer = self._get_offer(token)
        if offer.status != Offer.Status.SENT:
            return render(request, "crm/offer_commission_invalid.html", {
                "offer": offer, **_company_ctx(),
            })
        items = list(offer.items.all())
        return render(request, "crm/offer_commission_confirm.html", {
            "offer": offer,
            "items": items,
            "net_total": offer.net_total,
            "tax_amount": offer.tax_amount,
            "gross_total": offer.gross_total,
            **_company_ctx(),
        })

    def post(self, request, token):
        offer = self._get_offer(token)
        if offer.status != Offer.Status.SENT:
            return redirect("crm:offer_commission_confirm", token=token)

        # Legal evidence
        ip = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
        if "," in ip:
            ip = ip.split(",")[0].strip()
        ua = request.META.get("HTTP_USER_AGENT", "")[:500]

        offer.commissioned_at = timezone.now()
        offer.commissioned_method = "click"
        offer.commissioned_by_ip = ip
        offer.commissioned_by_user_agent = ua
        offer.status = Offer.Status.ACCEPTED
        offer.is_order_confirmation = True
        offer.save(update_fields=[
            "commissioned_at", "commissioned_method", "commissioned_by_ip",
            "commissioned_by_user_agent", "status", "is_order_confirmation",
        ])

        # Projekt auf Aktiv setzen
        if offer.project:
            offer.project.status = Project.Status.ACTIVE
            offer.project.save(update_fields=["status"])

        # AB-PDF an Kunden senden
        if offer.recipient_email:
            try:
                ab_pdf = _generate_offer_pdf_bytes(offer, request)
                msg = _build_email(
                    subject=f"Auftragsbestätigung {offer.display_number} – {offer.title}",
                    text_body=(
                        f"Sehr geehrte/r {offer.recipient_name or 'Damen und Herren'},\n\n"
                        f"vielen Dank für Ihren Auftrag! Anbei erhalten Sie Ihre "
                        f"Auftragsbestätigung {offer.display_number}.\n\n"
                        f"Mit freundlichen Grüßen"
                    ),
                    to=[offer.recipient_email],
                )
                msg.attach(f"{offer.display_number}.pdf", ab_pdf, "application/pdf")
                msg.send()
            except Exception:
                pass

        return redirect("crm:offer_commission_success", token=token)


class OfferCommissionSuccessView(View):
    """Public: Bestätigungsseite nach Online-Beauftragung."""

    def get(self, request, token):
        offer = get_object_or_404(Offer, commission_token=token)
        return render(request, "crm/offer_commission_success.html", {
            "offer": offer, **_company_ctx(),
        })


class OfferSignatureUploadView(EditOffersMixin, View):
    """Intern: Upload des unterschriebenen Angebots → Beauftragung per Unterschrift."""

    def post(self, request, pk):
        offer = get_object_or_404(Offer, pk=pk)
        pdf_file = request.FILES.get("signature_pdf")
        if not pdf_file:
            messages.error(request, "Bitte eine PDF-Datei hochladen.")
            return redirect("crm:offer_detail", pk=pk)

        offer.commissioned_signature_pdf = pdf_file
        offer.commissioned_at = timezone.now()
        offer.commissioned_method = "signature"
        offer.status = Offer.Status.ACCEPTED
        offer.is_order_confirmation = True
        offer.save(update_fields=[
            "commissioned_signature_pdf", "commissioned_at", "commissioned_method",
            "status", "is_order_confirmation",
        ])

        if offer.project:
            offer.project.status = Project.Status.ACTIVE
            offer.project.save(update_fields=["status"])

        messages.success(request, f"Unterschriebenes Angebot hochgeladen. {offer.offer_number} ist beauftragt, Projekt auf Aktiv gesetzt.")
        return redirect("crm:offer_detail", pk=pk)


class ProductCatalogAPIView(LoginRequiredMixin, View):
    """Returns JSON list of active catalog items for the quick-add modal."""
    def get(self, request):
        from .models import ProductCatalog
        items = ProductCatalog.objects.filter(is_active=True).values(
            "id", "name", "description", "unit", "quantity", "unit_price", "category", "billing_type"
        )
        # Convert Decimals to strings for JSON
        result = []
        for item in items:
            result.append({
                "id": item["id"],
                "name": item["name"],
                "description": item["description"],
                "unit": item["unit"],
                "quantity": str(item["quantity"]),
                "unit_price": str(item["unit_price"]),
                "category": item["category"],
                "billing_type": item["billing_type"],
            })
        return JsonResponse({"items": result})


# ---------------------------------------------------------------------------
# Quick Lead — Schnell-Lead anlegen
# ---------------------------------------------------------------------------

class QuickLeadCreateView(EditLeadsMixin, View):
    """Creates Account + Project from minimal data, optionally sends inquiry email."""

    def post(self, request):
        customer_name  = request.POST.get("customer_name", "").strip()
        topic          = request.POST.get("topic", "").strip()
        customer_email = request.POST.get("customer_email", "").strip()
        company        = request.POST.get("company", "").strip()

        if not customer_name or not topic:
            return JsonResponse({"error": "Name und Stichwort sind erforderlich."}, status=400)

        # Create Account
        account = Account.objects.create(
            name=customer_name,
            email=customer_email,
            account_type=Account.AccountType.COMPANY if company else Account.AccountType.PRIVATE,
        )

        # Create Project as LEAD
        project = Project.objects.create(
            name=topic,
            account=account,
            status=Project.Status.LEAD,
            created_by=request.user,
        )

        # Create LeadInquiry
        inquiry = LeadInquiry.objects.create(project=project)

        # Send inquiry email if email provided
        if customer_email:
            _send_inquiry_email(request, inquiry, customer_email, customer_name)
            inquiry.sent_at    = timezone.now()
            inquiry.expires_at = timezone.now() + timedelta(days=14)
            inquiry.save(update_fields=["sent_at", "expires_at"])

        return JsonResponse({
            "success":        True,
            "project_url":    request.build_absolute_uri(
                reverse("crm:project_detail", kwargs={"pk": project.pk})
            ),
            "project_number": project.project_number,
            "project_name":   project.name,
            "email_sent":     bool(customer_email),
        })


def _send_inquiry_email(request, inquiry, recipient_email, recipient_name):
    """Sends the inquiry link email to the customer."""
    inquiry_url = request.build_absolute_uri(
        reverse("crm:lead_inquiry_public", kwargs={"token": inquiry.token})
    )
    try:
        msg = _build_email(
            subject="Ihre Anfrage — bitte ergänzen Sie Ihre Kontaktdaten",
            text_body=(
                f"Guten Tag{' ' + recipient_name if recipient_name else ''},\n\n"
                "vielen Dank für Ihr Interesse. Um Ihre Anfrage optimal bearbeiten zu können, "
                "bitten wir Sie, Ihre Kontaktdaten und eine kurze Beschreibung Ihres Anliegens "
                "über folgenden Link zu ergänzen:\n\n"
                f"{inquiry_url}\n\n"
                "Dieser Link ist 14 Tage gültig.\n\n"
                "Mit freundlichen Grüßen"
            ),
            to=[recipient_email],
        )
        msg.send()
    except Exception:
        pass  # fail silently — lead is created regardless


class LeadInquiryPublicView(View):
    """Public (unauthenticated) form for customer to fill in their details."""

    def get(self, request, token):
        inquiry = self._get_inquiry(token)
        if inquiry is None:
            return render(request, "crm/lead_inquiry_expired.html", {})
        if inquiry.status == LeadInquiry.Status.SUBMITTED:
            return render(request, "crm/lead_inquiry_thankyou.html", {"inquiry": inquiry})
        from django.conf import settings as dj_settings
        return render(request, "crm/lead_inquiry_form.html", {
            "inquiry": inquiry,
            "project": inquiry.project,
            "google_maps_api_key": dj_settings.GOOGLE_MAPS_API_KEY,
            **_company_ctx(),
        })

    def post(self, request, token):
        inquiry = self._get_inquiry(token)
        if inquiry is None:
            return render(request, "crm/lead_inquiry_expired.html", {})
        if inquiry.status == LeadInquiry.Status.SUBMITTED:
            return render(request, "crm/lead_inquiry_thankyou.html", {"inquiry": inquiry})

        customer_type = request.POST.get("customer_type", LeadInquiry.CustomerType.PRIVATE)
        inquiry.customer_type       = customer_type
        inquiry.first_name          = request.POST.get("first_name", "").strip()
        inquiry.last_name           = request.POST.get("last_name", "").strip()
        inquiry.company_name        = request.POST.get("company_name", "").strip()
        inquiry.email               = request.POST.get("email", "").strip()
        inquiry.phone               = request.POST.get("phone", "").strip()
        inquiry.street              = request.POST.get("street", "").strip()
        inquiry.postal_code         = request.POST.get("postal_code", "").strip()
        inquiry.city                = request.POST.get("city", "").strip()
        inquiry.request_description = request.POST.get("request_description", "").strip()
        inquiry.invoice_email       = request.POST.get("invoice_email", "").strip()
        inquiry.status              = LeadInquiry.Status.SUBMITTED
        inquiry.submitted_at        = timezone.now()
        inquiry.save()

        # Update account with submitted data
        account = inquiry.project.account
        if account:
            is_company = customer_type == LeadInquiry.CustomerType.COMPANY
            account.account_type = Account.AccountType.COMPANY if is_company else Account.AccountType.PRIVATE
            if is_company and inquiry.company_name:
                account.name = inquiry.company_name
            elif not is_company:
                full_name = " ".join(p for p in [inquiry.first_name, inquiry.last_name] if p)
                if full_name:
                    account.name = full_name
            if inquiry.email:
                account.email = inquiry.email
            if inquiry.phone:
                account.phone = inquiry.phone
            if inquiry.street:
                account.address_line1 = inquiry.street
            if inquiry.postal_code:
                account.postal_code = inquiry.postal_code
            if inquiry.city:
                account.city = inquiry.city
            account.save()

        return render(request, "crm/lead_inquiry_thankyou.html", {"inquiry": inquiry})

    def _get_inquiry(self, token):
        try:
            inquiry = LeadInquiry.objects.select_related("project__account").get(token=token)
        except LeadInquiry.DoesNotExist:
            return None
        if inquiry.is_expired:
            return None
        return inquiry


class LeadInquiryImportView(EditOffersMixin, View):
    """Imports inquiry data into the offer creation form (pre-fills and redirects)."""

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        try:
            inquiry = project.lead_inquiry
        except LeadInquiry.DoesNotExist:
            messages.error(request, "Keine Anfrage vorhanden.")
            return redirect("crm:project_detail", pk=project.pk)

        if inquiry.status != LeadInquiry.Status.SUBMITTED:
            messages.warning(request, "Anfrage noch nicht eingereicht.")
            return redirect("crm:project_detail", pk=project.pk)

        # Mark as imported
        inquiry.status = LeadInquiry.Status.IMPORTED
        inquiry.save(update_fields=["status"])

        # Redirect to offer creation with pre-filled data via GET params
        from urllib.parse import urlencode
        params = urlencode({
            "recipient_name":    inquiry.customer_full_name,
            "recipient_email":   inquiry.email,
            "recipient_address": f"{inquiry.street}\n{inquiry.postal_code} {inquiry.city}".strip(),
            "description":       inquiry.request_description,
        })
        return redirect(f"{reverse('crm:offer_create', kwargs={'pk': project.pk})}?{params}")


# ---------------------------------------------------------------------------
# Lead-Pipeline
# ---------------------------------------------------------------------------

class LeadListView(AdminOrLeadMixin, ListView):
    """
    Zeigt alle Projekte in der Lead-Pipeline:
    status in [lead, offer_sent, offer_lost].
    """
    model               = Project
    template_name       = "crm/lead_list.html"
    context_object_name = "leads"
    paginate_by         = 50

    def get_queryset(self):
        f = self.request.GET.get("filter", "")
        qs = (
            Project.objects
            .filter(deleted_at__isnull=True)
            .select_related("account", "created_by")
            .prefetch_related("offers", "lead_inquiry")
        )
        if f == "open":
            qs = qs.filter(status__in=["lead", "offer_sent"])
        elif f == "lost":
            qs = qs.filter(status="offer_lost")
        else:
            qs = qs.filter(status__in=["lead", "offer_sent", "offer_lost"])
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filter"] = self.request.GET.get("filter", "")
        ctx["total_count"] = Project.objects.filter(
            status__in=["lead", "offer_sent", "offer_lost"],
            deleted_at__isnull=True,
        ).count()
        ctx["open_count"] = Project.objects.filter(
            status__in=["lead", "offer_sent"],
            deleted_at__isnull=True,
        ).count()
        ctx["lost_count"] = Project.objects.filter(
            status="offer_lost",
            deleted_at__isnull=True,
        ).count()
        return ctx


class LeadCommissionView(SendOffersMixin, View):
    """
    GET:  Bestätigungsseite — zeigt Projekt + Angebote, optional Datei-Upload.
    POST: Setzt Projektstatus auf 'active', Angebot auf 'accepted', speichert Dokument.
    """
    template_name = "crm/lead_commission.html"

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk, deleted_at__isnull=True)
        offers  = project.offers.all().order_by("-offer_date")
        return render(request, self.template_name, {
            "project": project,
            "offers":  offers,
            **self._base_ctx(),
        })

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk, deleted_at__isnull=True)

        # Accept the selected offer
        offer_pk = request.POST.get("offer_pk", "").strip()
        if offer_pk:
            try:
                offer = project.offers.get(pk=offer_pk)
                offer.status = Offer.Status.ACCEPTED
                offer.save(update_fields=["status"])
            except Offer.DoesNotExist:
                pass

        # Optional file upload
        uploaded_file = request.FILES.get("commission_file")
        if uploaded_file:
            title = request.POST.get("file_title", "").strip() or uploaded_file.name
            Document.objects.create(
                project=project,
                document_type=Document.DocumentType.COMMISSION,
                title=title,
                file=uploaded_file,
                uploaded_by=request.user,
            )

        # Activate the project
        project.status = Project.Status.ACTIVE
        project.save(update_fields=["status"])

        messages.success(
            request,
            f'Projekt „{project.name}" wurde beauftragt und ist jetzt aktiv.',
        )
        return redirect("crm:project_detail", pk=project.pk)

    def _base_ctx(self):
        return {
            "overdue_invoices_count": Invoice.objects.filter(
                status=Invoice.Status.SENT, due_date__lt=date.today()
            ).count(),
        }


# ---------------------------------------------------------------------------
# TextBlock Views
# ---------------------------------------------------------------------------

class TextBlockListView(AdminOrLeadMixin, ListView):
    model = TextBlock
    template_name = "crm/textblock_list.html"
    context_object_name = "textblocks"

    def get_queryset(self):
        return TextBlock.objects.all()


class TextBlockCreateView(EditTemplatesMixin, View):
    def get(self, request):
        form = TextBlockForm()
        return render(request, "crm/textblock_form.html", {"form": form, "page_title": "Neuer Textbaustein"})

    def post(self, request):
        form = TextBlockForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Textbaustein gespeichert.")
            return redirect("crm:textblock_list")
        return render(request, "crm/textblock_form.html", {"form": form, "page_title": "Neuer Textbaustein"})


class TextBlockUpdateView(EditTemplatesMixin, View):
    def get(self, request, pk):
        tb = get_object_or_404(TextBlock, pk=pk)
        form = TextBlockForm(instance=tb)
        return render(request, "crm/textblock_form.html", {"form": form, "page_title": "Textbaustein bearbeiten", "tb": tb})

    def post(self, request, pk):
        tb = get_object_or_404(TextBlock, pk=pk)
        form = TextBlockForm(request.POST, instance=tb)
        if form.is_valid():
            form.save()
            messages.success(request, "Textbaustein gespeichert.")
            return redirect("crm:textblock_list")
        return render(request, "crm/textblock_form.html", {"form": form, "page_title": "Textbaustein bearbeiten", "tb": tb})


class TextBlockDeleteView(EditTemplatesMixin, View):
    def post(self, request, pk):
        get_object_or_404(TextBlock, pk=pk).delete()
        messages.success(request, "Textbaustein gelöscht.")
        return redirect("crm:textblock_list")


class TextBlockSetDefaultView(EditTemplatesMixin, View):
    """Toggle: setzt diesen Baustein als Standard seiner Kategorie (oder hebt ihn auf)."""
    def post(self, request, pk):
        tb = get_object_or_404(TextBlock, pk=pk)
        if tb.is_default:
            tb.is_default = False
            tb.save(update_fields=["is_default"])
        else:
            # clear existing default in same category, then set new one
            TextBlock.objects.filter(category=tb.category, is_default=True).update(is_default=False)
            tb.is_default = True
            tb.save(update_fields=["is_default"])
        return redirect("crm:textblock_list")


class TextBlockAPIView(CRMMixin, View):
    """AJAX: Textbausteine per Kategorie und Scope laden oder Quick-Create."""
    def get(self, request):
        category = request.GET.get("category", "")
        scope    = request.GET.get("scope", "")
        qs = TextBlock.objects.all()
        if category:
            qs = qs.filter(category=category)
        if scope:
            qs = qs.filter(scope__in=[scope, "both"])
        return JsonResponse({"blocks": [{"id": tb.pk, "name": tb.name, "content": tb.content} for tb in qs]})

    def post(self, request):
        import json as _json
        data = _json.loads(request.body)
        name     = (data.get("name") or "").strip()
        category = (data.get("category") or "").strip()
        scope    = (data.get("scope") or "both").strip()
        content  = (data.get("content") or "").strip()
        if not name or not category or not content:
            return JsonResponse({"error": "Name, Kategorie und Inhalt sind Pflichtfelder."}, status=400)
        valid_cats = [c[0] for c in TextBlock.Category.choices]
        if category not in valid_cats:
            return JsonResponse({"error": "Ungültige Kategorie."}, status=400)
        tb = TextBlock.objects.create(name=name, category=category, scope=scope, content=content)
        return JsonResponse({"ok": True, "block": {"id": tb.pk, "name": tb.name, "content": tb.content}})


# ---------------------------------------------------------------------------
# Unit (Einheiten) CRUD
# ---------------------------------------------------------------------------

class UnitListView(AdminOrLeadMixin, ListView):
    model = Unit
    template_name = "crm/unit_list.html"
    context_object_name = "units"


class UnitCreateView(EditTemplatesMixin, View):
    def get(self, request):
        return render(request, "crm/unit_form.html", {
            "form": UnitForm(), "page_title": "Neue Einheit"
        })

    def post(self, request):
        form = UnitForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Einheit gespeichert.")
            return redirect("crm:unit_list")
        return render(request, "crm/unit_form.html", {
            "form": form, "page_title": "Neue Einheit"
        })


class UnitUpdateView(EditTemplatesMixin, View):
    def get(self, request, pk):
        unit = get_object_or_404(Unit, pk=pk)
        return render(request, "crm/unit_form.html", {
            "form": UnitForm(instance=unit), "unit": unit, "page_title": "Einheit bearbeiten"
        })

    def post(self, request, pk):
        unit = get_object_or_404(Unit, pk=pk)
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            form.save()
            messages.success(request, "Einheit gespeichert.")
            return redirect("crm:unit_list")
        return render(request, "crm/unit_form.html", {
            "form": form, "unit": unit, "page_title": "Einheit bearbeiten"
        })


class UnitDeleteView(EditTemplatesMixin, View):
    def post(self, request, pk):
        get_object_or_404(Unit, pk=pk).delete()
        messages.success(request, "Einheit gelöscht.")
        return redirect("crm:unit_list")


class UnitReorderView(EditTemplatesMixin, View):
    """AJAX POST: Reihenfolge der Einheiten via Drag-and-Drop speichern."""
    def post(self, request):
        import json
        data = json.loads(request.body)
        for idx, pk in enumerate(data.get("order", [])):
            Unit.objects.filter(pk=pk).update(sort_order=idx)
        return JsonResponse({"ok": True})


class UnitAPIView(CRMMixin, View):
    """AJAX: Alle Einheiten für Datalist/Autocomplete oder Quick-Create."""
    def get(self, request):
        units = list(Unit.objects.values_list("name", flat=True))
        return JsonResponse({"units": units})

    def post(self, request):
        import json as _json
        data = _json.loads(request.body)
        name = (data.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "Name ist ein Pflichtfeld."}, status=400)
        unit, created = Unit.objects.get_or_create(name=name)
        if not created:
            return JsonResponse({"error": f'Einheit „{name}" existiert bereits.'}, status=400)
        return JsonResponse({"ok": True, "name": unit.name})
