"""
Management-Command: Generiert deutsche Feiertage für ein Jahr.

Aufruf:
    python manage.py create_holidays          # aktuelles + nächstes Jahr
    python manage.py create_holidays 2025
    python manage.py create_holidays 2025 2026 2027
"""
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.worktrack.models import PublicHoliday


def _easter(year: int) -> datetime.date:
    """Gregorianischer Algorithmus für Ostersonntag (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(114 + h + l - 7 * m, 31)
    return datetime.date(year, month, day + 1)


def _holidays_for_year(year: int) -> list[dict]:
    easter = _easter(year)

    return [
        # Feste Feiertage
        {"date": datetime.date(year, 1, 1),   "name": "Neujahr"},
        {"date": datetime.date(year, 5, 1),   "name": "Tag der Arbeit"},
        {"date": datetime.date(year, 10, 3),  "name": "Tag der Deutschen Einheit"},
        {"date": datetime.date(year, 12, 25), "name": "1. Weihnachtstag"},
        {"date": datetime.date(year, 12, 26), "name": "2. Weihnachtstag"},
        # Firmenweit geschenkte halbe Tage (standard, kann deaktiviert werden)
        {"date": datetime.date(year, 12, 24), "name": "Heiligabend", "is_half_day": True,
         "note": "Firmenweit geschenkter halber Tag"},
        {"date": datetime.date(year, 12, 31), "name": "Silvester", "is_half_day": True,
         "note": "Firmenweit geschenkter halber Tag"},
        # Ostern-basierte Feiertage
        {"date": easter - datetime.timedelta(days=2), "name": "Karfreitag"},
        {"date": easter + datetime.timedelta(days=1), "name": "Ostermontag"},
        {"date": easter + datetime.timedelta(days=39), "name": "Christi Himmelfahrt"},
        {"date": easter + datetime.timedelta(days=50), "name": "Pfingstmontag"},
    ]


class Command(BaseCommand):
    help = "Generiert deutsche Feiertage (bundesweit) für ein oder mehrere Jahre."

    def add_arguments(self, parser):
        parser.add_argument(
            "years",
            nargs="*",
            type=int,
            help="Jahre (leer = aktuelles + nächstes Jahr)",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Bestehende Einträge überschreiben",
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        years = options["years"] or [today.year, today.year + 1]
        overwrite = options["overwrite"]

        created = 0
        skipped = 0
        updated = 0

        for year in years:
            self.stdout.write(f"\n  Jahr {year}:")
            for entry in _holidays_for_year(year):
                date     = entry["date"]
                name     = entry["name"]
                half_day = entry.get("is_half_day", False)
                note     = entry.get("note", "")

                if PublicHoliday.objects.filter(date=date).exists():
                    if overwrite:
                        PublicHoliday.objects.filter(date=date).update(
                            name=name, is_half_day=half_day, note=note
                        )
                        self.stdout.write(f"    ↻ {date} {name}")
                        updated += 1
                    else:
                        self.stdout.write(f"    – {date} {name} (bereits vorhanden, übersprungen)")
                        skipped += 1
                else:
                    PublicHoliday.objects.create(
                        date=date, name=name, is_half_day=half_day, note=note
                    )
                    self.stdout.write(f"    ✓ {date} {name}")
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFertig: {created} angelegt, {updated} aktualisiert, {skipped} übersprungen."
            )
        )
