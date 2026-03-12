"""
Management-Command: seed_demo
Legt realistische Demo-Daten an: 5 User, 3 neue Accounts,
10 weitere Projekte (inkl. archivierter), Beispielstunden.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.models import User
from apps.crm.models import Account, Project
from apps.worktrack.models import TimeEntry


class Command(BaseCommand):
    help = "Legt Demo-Daten an (User, Projekte, Stunden)."

    def handle(self, *args, **options):
        self._create_users()
        self._create_accounts()
        self._create_projects()
        self._create_time_entries()
        self.stdout.write(self.style.SUCCESS("Demo-Daten erfolgreich angelegt."))

    # ------------------------------------------------------------------

    def _create_users(self):
        users = [
            dict(first_name="Sophie",    last_name="Brandt",    email="sophie.brandt@direso.de",    role="project_manager"),
            dict(first_name="Max",       last_name="Fischer",   email="max.fischer@direso.de",       role="employee"),
            dict(first_name="Laura",     last_name="König",     email="laura.koenig@gt-immo.de",     role="employee"),
            dict(first_name="Thomas",    last_name="Müller",    email="thomas.mueller@gt-projekt.de",role="project_assistant"),
            dict(first_name="Jana",      last_name="Hoffmann",  email="jana.hoffmann@direso.de",     role="employee"),
        ]
        pw = make_password("donna2024!")
        for u in users:
            obj, created = User.objects.get_or_create(
                email=u["email"],
                defaults={
                    "username":   u["email"],
                    "first_name": u["first_name"],
                    "last_name":  u["last_name"],
                    "role":       u["role"],
                    "password":   pw,
                    "is_active":  True,
                    "totp_enabled": False,
                },
            )
            status = "angelegt" if created else "bereits vorhanden"
            self.stdout.write(f"  User {obj.email}: {status}")

    def _create_accounts(self):
        accounts = [
            dict(name="Bergmann & Söhne GmbH",        account_type="company", city="Stuttgart",  country="DE"),
            dict(name="Dr. Ingrid Wolff",              account_type="private", city="München",    country="DE"),
            dict(name="Novus Projektentwicklung GmbH", account_type="company", city="Frankfurt",  country="DE"),
            dict(name="Wohnbau Rheinland GmbH",        account_type="company", city="Düsseldorf", country="DE"),
        ]
        for a in accounts:
            obj, created = Account.objects.get_or_create(
                name=a["name"],
                defaults={**a, "is_active": True},
            )
            status = "angelegt" if created else "bereits vorhanden"
            self.stdout.write(f"  Account {obj.name}: {status}")

    def _create_projects(self):
        # Vorhandene Accounts holen
        def acc(name_part):
            return Account.objects.filter(name__icontains=name_part).first()

        pm = User.objects.filter(role="project_manager").first()
        emp1 = User.objects.filter(email="max.fischer@direso.de").first()
        emp2 = User.objects.filter(email="laura.koenig@gt-immo.de").first()
        emp3 = User.objects.filter(email="thomas.mueller@gt-projekt.de").first()
        emp4 = User.objects.filter(email="jana.hoffmann@direso.de").first()

        today = date.today()

        projects = [
            # Aktive GT Immo Projekte
            dict(name="Bürokomplex Hannover Süd",        company="gt_immo",    project_type="appraisal",
                 status="active",    account=acc("Bergmann"),
                 team_lead=pm, members=[emp1, emp2],
                 start=today - timedelta(days=45), end=today + timedelta(days=60),
                 budget_h=120, budget_a=Decimal("30600"), rate=Decimal("255")),

            dict(name="Wohnanlage Düsseldorf Nord",      company="gt_immo",    project_type="sale",
                 status="active",    account=acc("Wohnbau"),
                 team_lead=pm, members=[emp2],
                 start=today - timedelta(days=20), end=today + timedelta(days=90),
                 budget_h=80,  budget_a=Decimal("20400"), rate=Decimal("255")),

            dict(name="Umnutzung Gewerbe → Wohnen München", company="gt_immo", project_type="consulting",
                 status="offer_sent", account=acc("Wolff"),
                 team_lead=pm, members=[],
                 start=None, end=None,
                 budget_h=40,  budget_a=Decimal("10200"), rate=Decimal("255")),

            # GT Projekt
            dict(name="Neubau Logistikzentrum Frankfurt", company="gt_projekt", project_type="project_management",
                 status="active",    account=acc("Novus"),
                 team_lead=pm, members=[emp1, emp3],
                 start=today - timedelta(days=90), end=today + timedelta(days=180),
                 budget_h=320, budget_a=Decimal("81600"), rate=Decimal("255")),

            dict(name="Revitalisierung Altbau Stuttgart", company="gt_projekt", project_type="developer",
                 status="lead",      account=acc("Bergmann"),
                 team_lead=pm, members=[],
                 start=None, end=None,
                 budget_h=None, budget_a=None, rate=None),

            # DIRESO
            dict(name="Digitalisierung Maklerportal",    company="direso",     project_type="platform",
                 status="active",    account=acc("DIRESO"),
                 team_lead=pm, members=[emp1, emp4],
                 start=today - timedelta(days=30), end=today + timedelta(days=120),
                 budget_h=200, budget_a=Decimal("51000"), rate=Decimal("255")),

            dict(name="3D-Scan Gewerbepark Köln",        company="direso",     project_type="scan",
                 status="active",    account=acc("Bergmann"),
                 team_lead=pm, members=[emp3],
                 start=today - timedelta(days=10), end=today + timedelta(days=30),
                 budget_h=60,  budget_a=Decimal("15300"), rate=Decimal("255")),

            # Archivierte Projekte
            dict(name="Gutachten Erbengemeinschaft Hoffmann",  company="gt_immo", project_type="appraisal",
                 status="completed", account=acc("Erben"),
                 team_lead=pm, members=[emp2],
                 start=today - timedelta(days=200), end=today - timedelta(days=30),
                 budget_h=50,  budget_a=Decimal("12750"), rate=Decimal("255")),

            dict(name="Verkauf Bürogebäude Rheinland",    company="gt_immo",    project_type="sale",
                 status="cancelled", account=acc("Wohnbau"),
                 team_lead=pm, members=[],
                 start=today - timedelta(days=150), end=today - timedelta(days=60),
                 budget_h=None, budget_a=None, rate=None),

            dict(name="Website-Relaunch DIRESO 2023",    company="direso",     project_type="platform",
                 status="completed", account=acc("DIRESO"),
                 team_lead=pm, members=[emp1, emp4],
                 start=today - timedelta(days=365), end=today - timedelta(days=180),
                 budget_h=150, budget_a=Decimal("38250"), rate=Decimal("255")),
        ]

        for p in projects:
            obj, created = Project.objects.get_or_create(
                name=p["name"],
                defaults={
                    "company":      p["company"],
                    "project_type": p["project_type"],
                    "status":       p["status"],
                    "account":      p["account"],
                    "team_lead":    p["team_lead"],
                    "start_date":   p["start"],
                    "end_date":     p["end"],
                    "budget_hours":  p["budget_h"],
                    "budget_amount": p["budget_a"],
                    "hourly_rate":   p["rate"],
                },
            )
            if created and p["members"]:
                obj.team_members.set([m for m in p["members"] if m])
            status = "angelegt" if created else "bereits vorhanden"
            self.stdout.write(f"  Projekt '{obj.name}': {status}")

    def _create_time_entries(self):
        if TimeEntry.objects.count() > 0:
            self.stdout.write("  Zeiteinträge bereits vorhanden — übersprungen.")
            return

        users = list(User.objects.exclude(role="admin").filter(is_active=True))
        active_projects = list(Project.objects.filter(status__in=["active", "completed"]))

        if not active_projects:
            self.stdout.write("  Keine aktiven Projekte für Zeiteinträge gefunden.")
            return

        activities = [
            "Projektbearbeitung und Dokumentation",
            "Teambesprechung Projektstatus",
            "Kundenkommunikation per Mail und Telefon",
            "Ortstermin beim Kunden",
            "Rücksprache mit Auftraggeber",
            "Recherche und Unterlagenprüfung",
            "Angebotserstellung",
        ]

        today = date.today()
        entries_created = 0

        for user in users:
            # Je User ~15 Einträge über die letzten 8 Wochen
            user_projects = [
                p for p in active_projects
                if p.team_lead == user or user in p.team_members.all()
            ]
            if not user_projects:
                user_projects = active_projects[:3]

            for i in range(15):
                days_back = random.randint(1, 56)
                entry_date = today - timedelta(days=days_back)
                # Keine Wochenenden
                if entry_date.weekday() >= 5:
                    entry_date -= timedelta(days=entry_date.weekday() - 4)

                project = random.choice(user_projects)
                hours = Decimal(str(random.choice([1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 6.0, 8.0])))
                description = random.choice(activities)

                status = random.choice([
                    TimeEntry.Status.APPROVED,
                    TimeEntry.Status.APPROVED,
                    TimeEntry.Status.SUBMITTED,
                    TimeEntry.Status.DRAFT,
                ])

                TimeEntry.objects.create(
                    user=user,
                    project=project,
                    date=entry_date,
                    duration_hours=hours,
                    description=description,
                    is_billable=True,
                    status=status,
                )
                entries_created += 1

        self.stdout.write(f"  {entries_created} Zeiteinträge angelegt.")
