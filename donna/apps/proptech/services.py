"""
proptech/services.py

KI-Service zur Generierung von Baubeschreibungen via Claude API.
Jede hochgeladene Datei wird sofort beim Upload in Markdown konvertiert
und als wiederverwendbarer Wissenspool gespeichert.
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

Gliedere den Text immer in genau diese drei Abschnitte mit den folgenden Überschriften:

**Immobilie**
Beschreibe das Objekt ausführlich und konkret — mindestens 4–6 Sätze.
Geh ein auf: Gebäudeart und -charakter, Baujahr und Bauweise, Gesamtzustand,
Besonderheiten der Architektur oder des Grundrisses, Anzahl der Zimmer und Etagen,
Außenanlagen (Garten, Terrasse, Carport, Garage), Keller, Dachgeschoss.
Was macht dieses Objekt als Ganzes aus — was fällt beim ersten Anblick auf?
Beginne mit einem einleitenden Satz, der das Objekt auf den Punkt bringt.
Ton: einladend, professionell, konkret — keine leeren Allgemeinaussagen.

**Ausstattung**
Beschreibe die Ausstattungsmerkmale vollständig, detailliert und objektbezogen — mindestens 5–8 Sätze.
Geh systematisch durch alle erkennbaren Merkmale: Böden (Material, Zustand, welche Räume),
Bäder und WCs (Ausstattung, Fliesen, Sanitär, Himmelsrichtung falls erkennbar),
Küche (Einbauküche vorhanden? Zustand, Ausstattung), Heizungsanlage (Art, Energieträger, Baujahr falls bekannt),
Fenster und Verglasung, Einbauschränke und Stauraumlösungen, Smart-Home oder besondere Technik,
Kamin, Fußbodenheizung, Dachterrasse, Photovoltaik — was immer aus Fotos und Dokumenten erkennbar ist.
Beschreibe nicht nur was vorhanden ist, sondern auch den Zustand und das Wohngefühl.
Keine reine technische Aufzählung — verbinde Fakten mit Qualitätseindruck.

**Lage**
Beschreibe die Lage basierend auf deinem Wissen über den angegebenen Ort und Stadtteil.
Gehe ein auf: Infrastruktur (ÖPNV, Autobahnanbindung), Einkaufsmöglichkeiten,
Schulen und Kindergärten, Naherholung und Natur, Charakter des Viertels / der Gemeinde,
Entfernungen zu relevanten Zentren. Formuliere aus der Perspektive eines künftigen
Bewohners, der sich dort ein Leben aufbaut. Mindestens 3–4 Sätze.

Umgang mit Referenz-Exposés:
Du erhältst möglicherweise fertige Exposés aus vergangenen Projekten unserer Experten.
Diese sind keine bloßen Stilvorlagen — sie sind Beispiele dafür, wie erfahrene
Immobilienprofis konkrete Objekte mit Fotos und Dokumenten bewertet und in Texte
übersetzt haben. Lerne daraus:
- BEWERTUNGSLOGIK: Was haben die Experten als wichtig erachtet, was weggelassen?
  Wende dieselbe Prioritätensetzung auf das aktuelle Objekt an.
- AUSSTATTUNG: Wie wurden ähnliche Merkmale (Böden, Bäder, Küche, Garten etc.)
  bewertet und formuliert? Übertrage diese Bewertungen auf vergleichbare Merkmale.
- LAGE: Bei ähnlichem Standort: konkrete Infrastrukturinfos übernehmen, validieren,
  ans aktuelle Objekt anpassen und mit eigenem Wissen anreichern.
- STIL: Ton, Satzbau und Abstraktionsgrad als Muster übernehmen.
Alles Übernommene kritisch prüfen, anpassen und verbessern — nie 1:1 kopieren.

Übergreifende Stilregeln:
- Bildhafte, lebendige Sprache — keine leeren Floskeln ("einmalig", "traumhaft", "charmant")
- Sprich Käufer emotional an: Lebensqualität, Alltag, Potenzial
- Fließtext mit natürlichem Lesefluss — keine reinen Stichpunktlisten
- Schreibe auf Deutsch, Duzen vermeiden (neutral formulieren)
- Mehr ist besser: lieber ein Merkmal zu viel beschreiben als eines weglassen"""

MAX_TEMPLATE_CHARS = 8_000
MAX_FILE_MARKDOWN_CHARS = 6_000   # für Dokumente (PDFs, Pläne, Bauakte)
MAX_PHOTO_MARKDOWN_CHARS = 500    # für Fotos — kurze Beschreibung reicht, alle werden gesendet


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


CLAUDE_VISION_UNSUPPORTED = {".heic", ".heif", ".tiff", ".tif", ".bmp"}


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


def _pdf_to_markdown_via_claude(file_record, file_type_label: str, label: str) -> str:
    """
    Sendet ein PDF direkt an Claude (Haiku) als Dokument — funktioniert auch für
    gescannte/bildbasierte PDFs (Grundrisse, Pläne), die pypdf nicht lesen kann.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        with file_record.file.open("rb") as f:
            pdf_b64 = base64.standard_b64encode(f.read()).decode()

        if file_record.file_type == "plan":
            instruction = (
                "Beschreibe diesen Grundriss / Plan detailliert für eine KI-gestützte "
                "Objektbeschreibung. Analysiere:\n"
                "- Raumaufteilung und Anzahl der Zimmer\n"
                "- Erschließung und Wegführung\n"
                "- Lage von Bad, Küche, Wohnbereich\n"
                "- Besonderheiten wie Terrasse, Keller, Dachschrägen\n"
                "- Gesamteindruck der Grundrissqualität\n"
                "Schreibe präzise. Strukturiere als Markdown."
            )
        else:
            instruction = (
                "Beschreibe den Inhalt dieses Dokuments detailliert für eine KI-gestützte "
                "Immobilienbeschreibung. Extrahiere alle relevanten Informationen "
                "über das Objekt. Strukturiere als Markdown."
            )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {"type": "text", "text": instruction},
                ],
            }],
        )
        return f"# {file_type_label}: {label}\n\n{response.content[0].text}"
    except Exception as exc:
        logger.warning("PDF-Vision-Konvertierung fehlgeschlagen (%s): %s", label, exc)
        return ""


def convert_file_to_markdown(file_record) -> str:
    """
    Konvertiert eine hochgeladene Datei in Markdown.
    PDFs: erst pypdf, bei leerem Ergebnis (gescannte PDFs) → Claude Vision (Haiku).
    Bilder: Claude Vision (Haiku).
    Speichert immer etwas in markdown_content damit ⏳ verschwindet.
    """
    label = file_record.label or os.path.basename(file_record.file.name)
    file_type_label = file_record.get_file_type_display()
    ext = os.path.splitext(file_record.file.name)[1].lower()

    if file_record.is_pdf:
        text = _extract_pdf_text(file_record.file)
        if text:
            markdown = f"# {file_type_label}: {label}\n\n{text}"
        else:
            # Gescanntes PDF — direkt an Claude Vision schicken
            markdown = _pdf_to_markdown_via_claude(file_record, file_type_label, label)
            if not markdown:
                markdown = f"[{file_type_label}: {label} — PDF konnte nicht verarbeitet werden]"
    elif file_record.is_image:
        if ext in CLAUDE_VISION_UNSUPPORTED:
            markdown = f"[{file_type_label}: {label} — Format {ext} nicht unterstützt (bitte als JPG/PNG hochladen)]"
        else:
            markdown = _image_to_markdown_via_claude(file_record, file_type_label, label)
            if not markdown:
                markdown = f"[{file_type_label}: {label} — Bildbeschreibung fehlgeschlagen]"
    else:
        markdown = f"[{file_type_label}: {label} — Dateiformat wird nicht verarbeitet]"

    file_record.markdown_content = markdown
    file_record.save(update_fields=["markdown_content"])
    return markdown


def _image_to_markdown_via_claude(file_record, file_type_label: str, label: str) -> str:
    """
    Sendet ein Bild an Claude (Haiku — kostengünstig für Upload-Verarbeitung)
    und erhält eine detaillierte Markdown-Beschreibung zurück.
    """
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        b64, media_type = _image_to_base64(file_record.file)

        if file_record.file_type == "photo":
            instruction = (
                "Beschreibe dieses Immobilienfoto in maximal 3-4 Sätzen: "
                "Welcher Raum/Bereich? Böden, Wände, Einbauten, Zustand, Besonderheiten. "
                "Nur Fakten, kein Fließtext, keine Wertung."
            )
        elif file_record.file_type == "plan":
            instruction = (
                "Beschreibe diesen Grundriss / Plan detailliert für eine KI-gestützte "
                "Objektbeschreibung. Analysiere:\n"
                "- Raumaufteilung und Anzahl der Zimmer\n"
                "- Erschließung und Wegführung\n"
                "- Lage von Bad, Küche, Wohnbereich\n"
                "- Besonderheiten wie Terrasse, Keller, Dachschrägen\n"
                "- Gesamteindruck der Grundrissqualität\n"
                "Schreibe präzise. Strukturiere als Markdown."
            )
        else:
            instruction = (
                "Beschreibe dieses Dokument / Bild detailliert für eine KI-gestützte "
                "Immobilienbeschreibung. Extrahiere alle relevanten Informationen "
                "über das Objekt (Zustand, Ausstattung, Besonderheiten). "
                "Strukturiere als Markdown."
            )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": instruction},
                ],
            }],
        )
        description = response.content[0].text
        return f"# {file_type_label}: {label}\n\n{description}"
    except Exception as exc:
        logger.warning("Bild-zu-Markdown fehlgeschlagen (%s): %s", label, exc)
        return ""


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

        # Referenz-Exposés / Vorlagen (max. 3)
        # Passende Gebäudetyp-Vorlagen zuerst, dann allgemeine
        from django.db.models import Case, When, IntegerField
        building_type_key = report.building_type or ""
        templates = (
            DescriptionTemplate.objects
            .filter(role=report.role, is_active=True)
            .annotate(match=Case(
                When(building_type=building_type_key, then=0),
                When(building_type="", then=1),
                default=2,
                output_field=IntegerField(),
            ))
            .order_by("match", "uploaded_at")
        )
        for tpl in templates[:3]:
            tpl_text = tpl.extracted_text
            if tpl_text:
                snippet = tpl_text[:MAX_TEMPLATE_CHARS]
                content.append({
                    "type": "text",
                    "text": (
                        f"## Referenz-Exposé aus vergangenen Projekten: {tpl.name}"
                        + (f" [{tpl.get_building_type_display()}]" if tpl.building_type else "")
                        + (f" — {' '.join(filter(None, [tpl.street, tpl.postal_code, tpl.city]))}" if any([tpl.street, tpl.city]) else "")
                        + "\n\n"
                        f"{snippet}\n\n"
                        "[Analysiere dieses Referenz-Exposé als Beispiel dafür, wie unsere Experten "
                        "ein Objekt bewertet und beschrieben haben:\n"
                        "1. BEWERTUNGSLOGIK: Welche Merkmale haben die Experten als Stärken "
                        "hervorgehoben? Was wurde weggelassen? Welche Prioritäten sind erkennbar?\n"
                        "2. AUSSTATTUNG: Welche Ausstattungsmerkmale wurden wie bewertet und formuliert? "
                        "Übernimm diese Bewertungslogik für ähnliche Merkmale beim aktuellen Objekt.\n"
                        "3. LAGE: Wenn das Referenzobjekt in einer vergleichbaren Lage liegt "
                        "(gleiche Stadt, Stadtteil oder ähnliches Umfeld), übernimm konkrete "
                        "Lageinformationen als Ausgangsbasis.\n"
                        "4. STIL & SPRACHE: Übernimm den Ton, die Satzkonstruktionen und den "
                        "Abstraktionsgrad als Stilvorlage.\n"
                        "Wichtig: Validiere alle übernommenen Inhalte — passe sie präzise ans aktuelle "
                        "Objekt an, verbessere und ergänze sie. Kopiere keine Formulierungen 1:1.]"
                    ),
                })

        # Hochgeladene Dateien als Markdown-Pool
        # Noch nicht konvertierte Dateien jetzt aufbereiten (lazy conversion)
        pending = report.files.filter(markdown_content="").order_by("file_type", "uploaded_at")
        for f in pending:
            try:
                convert_file_to_markdown(f)
            except Exception as exc:
                logger.warning("Markdown-Konvertierung übersprungen (%s): %s", f.filename, exc)

        # Dokumente (Bauakte, Pläne, Sonstiges) vollständig einbeziehen
        file_sections = []
        for f in report.files.exclude(file_type="photo").order_by("file_type", "uploaded_at"):
            if f.markdown_content:
                file_sections.append(f.markdown_content[:MAX_FILE_MARKDOWN_CHARS])

        # Fotos: alle einbeziehen, aber kurz gefasst (~500 Zeichen pro Foto)
        for f in report.files.filter(file_type="photo").order_by("uploaded_at"):
            if f.markdown_content:
                file_sections.append(f.markdown_content[:MAX_PHOTO_MARKDOWN_CHARS])

        if file_sections:
            content.append({
                "type": "text",
                "text": (
                    "## Hochgeladene Unterlagen (KI-aufbereitetes Markdown)\n\n"
                    "Die folgenden Beschreibungen wurden automatisch aus den hochgeladenen "
                    "Fotos, Grundrissen und Dokumenten generiert. Nutze sie als primäre "
                    "Informationsquelle für Ausstattung und Zustand des Objekts.\n\n"
                    + "\n\n---\n\n".join(file_sections)
                ),
            })

        # Abschluss-Prompt
        if report.role == "gutachter":
            closing = (
                "Bitte erstelle jetzt die Gutachter-Baubeschreibung (Verkehrswertgutachten) "
                "für dieses Objekt auf Basis aller oben bereitgestellten Informationen."
            )
        else:
            addr_parts = list(filter(None, [report.street, report.postal_code, report.city]))
            addr = " ".join(addr_parts)
            closing = (
                "Bitte erstelle jetzt die Makler-Objektbeschreibung (Exposé) "
                "für dieses Objekt auf Basis aller oben bereitgestellten Informationen. "
                "Strukturiere den Text in die drei Abschnitte: Immobilie, Ausstattung, Lage. "
            )
            if addr:
                closing += (
                    f"Für den Abschnitt 'Lage' nutze dein Wissen über den Standort ({addr}) — "
                    "beschreibe Infrastruktur, ÖPNV, Schulen, Einkauf, Naherholung und Charakter "
                    "des Viertels/der Gemeinde so konkret wie möglich."
                )
        content.append({"type": "text", "text": closing})

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=8192,
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
            lines.append(f"Gebäudeart: {report.get_building_type_display()}")
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
