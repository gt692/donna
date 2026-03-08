"""
core/context_processors.py

Stellt allen Templates globale Kontext-Variablen zur Verfügung.
"""


def pending_approvals(request):
    """Zählt ausstehende Buchungen für den Sidebar-Badge."""
    if not request.user.is_authenticated:
        return {}
    if not request.user.can_approve_time_entries():
        return {"pending_approvals_count": 0}

    from apps.worktrack.models import TimeEntry
    count = TimeEntry.objects.filter(
        status=TimeEntry.Status.SUBMITTED,
        user__in=request.user.get_approvable_users(),
    ).count()
    return {"pending_approvals_count": count}
