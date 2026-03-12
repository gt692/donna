"""
dashboard/templatetags/donna_filters.py

Custom Template-Filter für das Donna Dashboard.
"""
from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def eur_de(value):
    """
    Formatiert eine Dezimalzahl als deutschen EUR-String.
    Beispiel: Decimal("1234567.50") → "1.234.568 €"
    """
    if value is None:
        return "—"
    try:
        rounded = int(round(Decimal(str(value))))
        formatted = f"{rounded:,}".replace(",", ".")
        return f"{formatted} €"
    except (ValueError, TypeError):
        return "—"


@register.filter
def get_item(d, key):
    """Dict-Lookup mit variablem Schlüssel, z.B. {{ company_colors|get_item:project.company }}"""
    if isinstance(d, dict):
        return d.get(key, "")
    return ""


@register.filter
def pct_color(value):
    """
    Gibt eine Tailwind-Farbklasse zurück basierend auf dem Prozentwert.
    ≥75 → green, ≥50 → amber, sonst → blue
    """
    try:
        v = int(value)
    except (ValueError, TypeError):
        return "blue"
    if v >= 75:
        return "green"
    if v >= 50:
        return "amber"
    return "blue"
