"""
proptech/services.py

KI-Service zur Generierung von Baubeschreibungen via Claude API.
"""
import base64
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_GUTACHTER = """Du bist ein erfahrener Sachverständiger für Immobilienbewertung \
(zertifiziert nach DIN EN ISO/IEC 17024).
Erstelle eine sachliche, technisch präzise Baubeschreibung im Stil eines \
Verkehrswertgutachtens gemäß ImmoWertV.

Beschreibe die Immobilie systematisch nach folgenden Aspekten \
(soweit aus den Unterlagen erkennbar):
- Gebäudeart, Baujahr, Bauweise, Tragwerk/Konstruktion
- Dach (Dachform, Eindeckung, Zustand)
- Fassade und Außenwände
- Fenster und Außentüren
- Grundriss und Raumaufteilung
- Fußböden, Wand- und Deckenbeläge
- Sanitärausstattung und Bäder
- Heizungsanlage und Warmwasserversorgung
- Elektroinstallation
- Modernisierungen und Renovierungen (mit Jahreszahlen wenn bekannt)
- Beurteilung des Bauzustandes

Schreibe fachlich korrekt, vollständig und sachlich ohne Wertungen oder \
Marketingformulierungen. Verwende Fachterminologie. \
Wenn bestimmte Informationen nicht aus den Unterlagen ersichtlich sind, \
lasse diese Punkte weg. Strukturiere den Text in klare Absätze je Gebäudeteil."""

SYSTEM_PROMPT_MAKLER = """Du bist ein erfahrener Immobilienmakler und Texter für Immobilienexposés.
Erstelle eine ansprechende, verkaufsfördernde Objektbeschreibung für ein Exposé.

Dein Ziel:
- Hebe die Highlights und Stärken der Immobilie hervor
- Verwende positive, bildhafte und lebendige Sprache
- Sprich potenzielle Käufer emotional an (Lebensqualität, Wohngefühl, Potenzial)
- Verzichte auf übermäßig technische Details — fokussiere auf das Erleben
- Strukturiere in 3–5 Absätze mit natürlichem Lesefluss
- Der Ton ist einladend und professionell, nicht reißerisch

Beginne mit einem einleitenden Satz, der die Immobilie auf den Punkt bringt. \
Vermeide Floskeln wie "Einzigartig" oder "einmalige Gelegenheit"."""

MAX_IMAGES = 10
MAX_PDF_CHARS = 8_000


def _extract_pdf_text(file_field) -> str:
    """Extrahiert Text aus einem PDF-FileField via pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_field.path)
        texts = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n\n".join(t.strip() for t in texts)
    except Exception as exc:
        logger.warning("PDF-Extraktion fehlgeschlagen: %s", exc)
        return ""


def _image_to_base64(file_field) -> tuple:
    """Gibt (base64_data, media_type) zurück."""
    ext = os.path.splitext(file_field.name)[1].lower()
    media_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_map.get(ext, "image/jpeg")
    with file_field.open("rb") as f:
        return base64.standard_b64encode(f.read()).decode(), media_type


class PropertyDescriptionService:
    def generate(self, report) -> str:
        import anthropic
        from .models import DescriptionTemplate

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        system = SYSTEM_PROMPT_GUTACHTER if report.role == "gutachter" else SYSTEM_PROMPT_MAKLER

        content = []

        # Hardfacts
        facts = self._build_hardfacts(report)
        if facts:
            content.append({"type": "text", "text": f"## Objektdaten\n\n{facts}"})

        # Stil-Vorlagen (max. 2)
        templates = DescriptionTemplate.objects.filter(role=report.role, is_active=True)
        for tpl in templates[:2]:
            if tpl.extracted_text:
                snippet = tpl.extracted_text[:MAX_PDF_CHARS]
                content.append({
                    "type": "text",
                    "text": f"## Stil-Referenz: {tpl.name}\n\n{snippet}",
                })

        # Dokumente als Text (Bauakte, sonstige, Pläne als PDFs)
        doc_files = report.files.filter(file_type__in=["bauakte", "misc", "plan"])
        pdf_texts = []
        for f in doc_files:
            if f.is_pdf:
                text = _extract_pdf_text(f.file)
                if text:
                    pdf_texts.append(
                        f"### {f.get_file_type_display()}: {f.label or f.filename}\n\n{text[:MAX_PDF_CHARS]}"
                    )
        if pdf_texts:
            content.append({
                "type": "text",
                "text": "## Hochgeladene Dokumente\n\n" + "\n\n---\n\n".join(pdf_texts),
            })

        # Bilder (Fotos + Pläne als Bilder)
        image_files = list(report.files.filter(file_type__in=["photo", "plan"]))
        image_count = 0
        for f in image_files:
            if image_count >= MAX_IMAGES:
                break
            if f.is_image:
                try:
                    b64, media_type = _image_to_base64(f.file)
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    })
                    image_count += 1
                except Exception as exc:
                    logger.warning("Bild konnte nicht geladen werden (%s): %s", f.filename, exc)

        # Abschluss-Prompt
        role_label = (
            "Gutachter-Baubeschreibung (Verkehrswertgutachten)"
            if report.role == "gutachter"
            else "Makler-Objektbeschreibung (Exposé)"
        )
        content.append({
            "type": "text",
            "text": (
                f"Bitte erstelle jetzt die {role_label} für dieses Objekt auf Basis "
                "aller oben bereitgestellten Informationen und Unterlagen."
            ),
        })

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        return response.content[0].text

    def _build_hardfacts(self, report) -> str:
        lines = []
        addr_parts = filter(None, [report.street, report.postal_code, report.city])
        addr = " ".join(addr_parts)
        if addr:
            lines.append(f"Adresse: {addr}")
        if report.building_type:
            lines.append(f"Gebäudeart: {report.building_type}")
        if report.year_of_construction:
            lines.append(f"Baujahr: {report.year_of_construction}")
        if report.living_area:
            lines.append(f"Wohnfläche: {report.living_area} m²")
        if report.plot_area:
            lines.append(f"Grundstücksfläche: {report.plot_area} m²")
        if report.number_of_rooms:
            lines.append(f"Zimmeranzahl: {report.number_of_rooms}")
        if report.number_of_floors:
            lines.append(f"Stockwerke: {report.number_of_floors}")
        if report.condition:
            lines.append(f"Zustand: {report.condition}")
        if report.additional_notes:
            lines.append(f"\nZusätzliche Hinweise:\n{report.additional_notes}")
        return "\n".join(lines)
