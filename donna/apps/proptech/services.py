"""
proptech/services.py

KI-Service zur Generierung von Baubeschreibungen via Claude API.

Pipeline:
  Fotos  → Claude Haiku Vision (rollenspezifischer Prompt, 6-8 Sätze)
  PDFs   → pypdf (Qualitätscheck: >200 Zeichen/Seite)
             └ zu wenig Text → Claude Haiku als Dokument (auch für gescannte PDFs)
  HEIC   → wird bereits beim Upload zu JPEG konvertiert (pillow-heif in views.py)

Lazy Conversion: findet beim ersten Generieren statt, Ergebnis wird in
PropertyReportFile.markdown_content gespeichert und danach wiederverwendet.
"""
import base64
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_GUTACHTER = """Du bist ein erfahrener Sachverständiger für Immobilienbewertung \
(zertifiziert nach DIN EN ISO/IEC 17024).
Erstelle eine sachliche, technisch präzise Baubeschreibung im Stil eines \
Verkehrswertgutachtens gemäß ImmoWertV.

Beschreibe die Immobilie systematisch nach folgenden Aspekten \
(soweit aus den Unterlagen erkennbar):
- Gebäudeart, Baujahr, Bauweise, Tragwerk/Konstruktion
- Dach (Dachform, Eindeckung, Zustand)
- Fassade und Außenwände (Material, Dämmung, Zustand)
- Fenster und Außentüren (Material, Verglasung, Zustand)
- Grundriss und Raumaufteilung
- Fußböden (Material je Bereich, Zustand)
- Wand- und Deckenbeläge (Material, Zustand)
- Sanitärausstattung und Bäder (Ausstattungsstandard, Baujahr/Erneuerung)
- Heizungsanlage und Warmwasserversorgung (Art, Energieträger, Baujahr)
- Elektroinstallation
- Modernisierungen und Renovierungen (mit Jahreszahlen wenn bekannt)
- Sichtbare Schäden, Mängel oder Auffälligkeiten
- Beurteilung des Bauzustandes insgesamt

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
Bäder und WCs (Ausstattung, Fliesen, Sanitär), Küche (Einbauküche vorhanden? Zustand, Ausstattung),
Heizungsanlage (Art, Energieträger), Fenster und Verglasung, Einbauschränke, Smart-Home oder
besondere Technik, Kamin, Fußbodenheizung, Terrasse, Photovoltaik — was immer erkennbar ist.
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
- AUSSTATTUNG: Wie wurden ähnliche Merkmale bewertet und formuliert?
- LAGE: Bei vergleichbarem Standort konkrete Infos übernehmen, validieren, anpassen.
- STIL: Ton, Satzbau und Abstraktionsgrad als Muster übernehmen.
Alles kritisch prüfen, anpassen und verbessern — nie 1:1 kopieren.

Übergreifende Stilregeln:
- Bildhafte, lebendige Sprache — keine leeren Floskeln ("einmalig", "traumhaft")
- Käufer emotional ansprechen: Lebensqualität, Alltag, Potenzial
- Fließtext mit natürlichem Lesefluss
- Schreibe auf Deutsch, neutral (kein Duzen)
- Mehr ist besser: lieber ein Merkmal zu viel beschreiben als eines weglassen"""

# ── Foto-Konvertierungs-Prompts (rollenspezifisch) ────────────────────────────

PHOTO_PROMPT_GUTACHTER = (
    "Beschreibe dieses Immobilienfoto für ein Verkehrswertgutachten präzise und vollständig "
    "in 6–8 Sätzen. Analysiere:\n"
    "- Welcher Raum oder Bereich ist zu sehen?\n"
    "- Bodenbelag: Material (Parkett, Fliesen, Teppich, Laminat …), Zustand, sichtbare Schäden\n"
    "- Wände und Decken: Oberfläche, Zustand, Feuchtigkeitsschäden, Risse\n"
    "- Einbauten und Ausstattung: Fenster (Material, Verglasung), Türen, Heizkörper, Sanitär\n"
    "- Sichtbare Mängel, Schäden oder Modernisierungsbedarf\n"
    "- Baualterseinschätzung der sichtbaren Elemente\n"
    "Nur sachliche Fakten, keine Werturteile."
)

PHOTO_PROMPT_MAKLER = (
    "Beschreibe dieses Immobilienfoto für ein Exposé ansprechend und konkret in 6–8 Sätzen. "
    "Analysiere:\n"
    "- Welcher Raum oder Bereich? Größeneindruck, Raumgefühl, Helligkeit\n"
    "- Bodenbelag: Material und Qualitätseindruck\n"
    "- Ausstattungsmerkmale: Einbauten, Küche, Bad, Kamin, Terrasse, Besonderheiten\n"
    "- Zustand und Modernisierungsgrad: wirkt renoviert, gepflegt, hochwertig?\n"
    "- Atmosphäre und Wohngefühl: was macht den Raum attraktiv für Käufer?\n"
    "Konkrete Fakten mit Qualitätseindruck verbinden. Keine leeren Floskeln."
)

# ── Plan/Dokument-Prompts ─────────────────────────────────────────────────────

PLAN_PROMPT = (
    "Beschreibe diesen Grundriss / Plan detailliert für eine Immobilienbeschreibung. "
    "Analysiere:\n"
    "- Raumaufteilung: Anzahl und Art der Zimmer, Größenverhältnisse\n"
    "- Erschließung: Eingangssituation, Flure, Treppenhaus\n"
    "- Lage von Bad, Küche, Wohnbereich, Schlafzimmer\n"
    "- Besonderheiten: Terrasse, Balkon, Keller, Garage, Dachschrägen\n"
    "- Grundrissqualität: Funktionalität, Raumfluss, Tageslicht-Situation\n"
    "Strukturiere als Markdown mit klaren Absätzen."
)

BAUAKTE_PROMPT_GUTACHTER = (
    "Analysiere dieses Dokument aus einer Bauakte für ein Verkehrswertgutachten. "
    "Extrahiere alle relevanten technischen Informationen:\n"
    "- Baugenehmigungen, Baujahre, Bauabschnitte\n"
    "- Materialangaben, Konstruktionsdetails, Tragwerk\n"
    "- Nachträgliche Änderungen, Anbauten, Modernisierungen\n"
    "- Technische Anlagen (Heizung, Elektro, Sanitär)\n"
    "- Behördliche Auflagen oder Einschränkungen\n"
    "- Sichtbare Mängel oder Schadensdokumentation\n"
    "Strukturiere als Markdown. Fachterminologie verwenden."
)

BAUAKTE_PROMPT_MAKLER = (
    "Analysiere dieses Dokument aus einer Bauakte. "
    "Extrahiere alle Informationen, die für eine Exposé-Beschreibung relevant sind:\n"
    "- Baujahr und Bauabschnitte\n"
    "- Modernisierungen und Renovierungen (mit Jahreszahlen)\n"
    "- Besondere Ausstattungsmerkmale\n"
    "- Wohnfläche, Nutzfläche, Raumanzahl laut Genehmigung\n"
    "Strukturiere als Markdown."
)

FLAECHENBERECHNUNG_PROMPT = (
    "Analysiere diese Flächenberechnung / Kubaturberechnung und extrahiere alle Werte strukturiert:\n"
    "- Wohnfläche gesamt (nach WohnflächenVO) und je Raum/Geschoss\n"
    "- Nutzfläche, Nebenfläche, Verkehrsfläche (falls ausgewiesen)\n"
    "- Brutto-Grundfläche (BGF) und Brutto-Rauminhalt (BRI/Kubatur)\n"
    "- Aufschlüsselung je Geschoss (KG, EG, OG, DG, Garage)\n"
    "- Balkon-/Terrassen-/Loggiaflächen und deren Anrechnungsfaktor\n"
    "- Kellerräume und Nebengebäude\n"
    "Strukturiere als Markdown-Tabelle soweit möglich."
)

BAUBESCHREIBUNG_ORIGINAL_PROMPT = (
    "Analysiere diese originale Baubeschreibung / dieses Leistungsverzeichnis aus der Bauplanung. "
    "Extrahiere alle technischen Angaben strukturiert:\n"
    "- Konstruktion und Tragwerk (Bauweise, Mauerwerk, Decken, Dach)\n"
    "- Fassade und Außenwände (Material, Dämmung, U-Wert falls angegeben)\n"
    "- Fenster und Außentüren (Material, Verglasung, Uw-Wert)\n"
    "- Dach (Form, Eindeckung, Dämmung)\n"
    "- Innenausbau: Böden je Raum, Wand- und Deckenoberflächen\n"
    "- Sanitär: Bäder, WCs, Ausstattungsstandard\n"
    "- Heizungsanlage: Art, Energieträger, Hersteller falls angegeben\n"
    "- Elektroinstallation\n"
    "- Besondere Ausstattung (Fußbodenheizung, Kamin, Smart-Home etc.)\n"
    "Strukturiere als Markdown. Dies ist eine primäre Informationsquelle für Materialien und Ausstattungsstandard."
)

GRUNDBUCH_PROMPT = (
    "Analysiere dieses Dokument (Grundbuchauszug, Baulastenauskunft, Altlastenauskunft, "
    "Denkmalschutzauskunft oder Erschließungsbeitragsbescheid) und extrahiere alle "
    "wertrelevanten Eintragungen strukturiert:\n\n"
    "**Grundbuch:**\n"
    "- Abt. I: Eigentümer und Eigentumsanteile\n"
    "- Abt. II: Alle Lasten und Beschränkungen (Wegerechte, Nießbrauch, Vorkaufsrecht, "
    "Reallasten, Wohnrechte, Leitungsrechte) — mit genauer Bezeichnung und Inhalt\n"
    "- Abt. III: Grundpfandrechte (Hypotheken, Grundschulden) — Betrag und Gläubiger\n\n"
    "**Baulasten:** Art und Umfang der eingetragenen Baulasten\n"
    "**Altlasten:** Kontaminationsstatus, Altablagerungen, Verdachtsflächenstatus\n"
    "**Denkmalschutz:** Schutzumfang (Einzeldenkmal, Ensemble), Auflagen, Fördermöglichkeiten\n"
    "**Erschließung:** Noch offene Beiträge, Erschließungsstand\n\n"
    "Hebe besonders hervor: Was beeinflusst den Wert oder die Nutzbarkeit des Objekts negativ?"
)

ENERGIEAUSWEIS_PROMPT = (
    "Analysiere diesen Energieausweis und extrahiere alle relevanten Daten strukturiert:\n"
    "- Art des Ausweises (Bedarfs- oder Verbrauchsausweis)\n"
    "- Energieeffizienzklasse (A+ bis H)\n"
    "- Endenergiebedarf oder -verbrauch (kWh/(m²·a))\n"
    "- Primärenergiebedarf (kWh/(m²·a))\n"
    "- Hauptenergieträger (Gas, Öl, Wärmepumpe, Fernwärme etc.)\n"
    "- Baujahr des Gebäudes laut Ausweis\n"
    "- Wesentliche Modernisierungsempfehlungen\n"
    "- Ausstellungsdatum und Gültigkeit\n"
    "Strukturiere als Markdown."
)

DOC_PROMPT = (
    "Analysiere dieses Dokument und extrahiere alle Informationen, die für eine "
    "Immobilienbeschreibung (Gutachten oder Exposé) relevant sind. "
    "Strukturiere als Markdown."
)

# ── Kontext-Limits ────────────────────────────────────────────────────────────

MAX_TEMPLATE_CHARS = 8_000
MAX_FILE_MARKDOWN_CHARS = 6_000
MAX_PHOTO_MARKDOWN_CHARS = 1_200   # erhöht: Fotos sind das wichtigste Element

# Qualitätsschwelle pypdf: weniger als X Zeichen pro Seite → PDF ist gescannt
MIN_CHARS_PER_PAGE = 200

CLAUDE_VISION_UNSUPPORTED = {".heic", ".heif", ".tiff", ".tif", ".bmp"}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _extract_pdf_text(file_field) -> tuple[str, int]:
    """Extrahiert Text aus einem PDF. Gibt (text, num_pages) zurück."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_field.path)
        num_pages = len(reader.pages)
        texts = [page.extract_text() for page in reader.pages if page.extract_text()]
        return "\n\n".join(t.strip() for t in texts), num_pages
    except Exception as exc:
        logger.warning("PDF-Extraktion fehlgeschlagen: %s", exc)
        return "", 0


def _pdf_text_is_sufficient(text: str, num_pages: int) -> bool:
    """True wenn pypdf genug Text geliefert hat (kein gescanntes PDF)."""
    if not text.strip() or num_pages == 0:
        return False
    return len(text.strip()) / num_pages >= MIN_CHARS_PER_PAGE


def _image_to_base64(file_field) -> tuple[str, str]:
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


def _call_haiku(messages: list, max_tokens: int = 1024) -> str:
    """Hilfsfunktion: Claude Haiku aufrufen und Text zurückgeben."""
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("Haiku-API-Fehler: %s", exc)
        return ""


def _image_to_markdown(file_record, prompt: str, label: str, file_type_label: str) -> str:
    """Bild → Markdown via Claude Haiku Vision."""
    try:
        b64, media_type = _image_to_base64(file_record.file)
        text = _call_haiku([{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }], max_tokens=1024)
        return f"# {file_type_label}: {label}\n\n{text}" if text else ""
    except Exception as exc:
        logger.warning("Bild-zu-Markdown fehlgeschlagen (%s): %s", label, exc)
        return ""


def _pdf_to_markdown_via_vision(file_record, prompt: str, label: str, file_type_label: str) -> str:
    """Gescanntes PDF → Markdown via Claude Haiku (Document API)."""
    try:
        with file_record.file.open("rb") as f:
            pdf_b64 = base64.standard_b64encode(f.read()).decode()
        text = _call_haiku([{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": prompt},
            ],
        }], max_tokens=2048)
        return f"# {file_type_label}: {label}\n\n{text}" if text else ""
    except Exception as exc:
        logger.warning("PDF-Vision fehlgeschlagen (%s): %s", label, exc)
        return ""


# ── Haupt-Konvertierungsfunktion ──────────────────────────────────────────────

def _get_doc_prompt(file_type: str, is_gutachter: bool) -> str:
    """Gibt den passenden Extraktions-Prompt für einen Nicht-Foto-Dateityp zurück."""
    return {
        "plan":                   PLAN_PROMPT,
        "flaechenberechnung":     FLAECHENBERECHNUNG_PROMPT,
        "baubeschreibung_original": BAUBESCHREIBUNG_ORIGINAL_PROMPT,
        "bauakte":                BAUAKTE_PROMPT_GUTACHTER if is_gutachter else BAUAKTE_PROMPT_MAKLER,
        "energieausweis":         ENERGIEAUSWEIS_PROMPT,
        "grundbuch":              GRUNDBUCH_PROMPT,
    }.get(file_type, BAUAKTE_PROMPT_GUTACHTER if is_gutachter else DOC_PROMPT)


def convert_file_to_markdown(file_record, role: str = "") -> str:
    """
    Konvertiert eine hochgeladene Datei in Markdown und speichert das Ergebnis.

    Pipeline:
      Foto  → Claude Haiku Vision (rollenspezifischer Prompt)
      PDF   → pypdf (Qualitätscheck) → bei unzureichendem Text: Claude Vision
      Sonst → Fallback-Marker

    Speichert immer etwas, damit ⏳ nie dauerhaft bleibt.
    """
    label = file_record.label or os.path.basename(file_record.file.name)
    file_type_label = file_record.get_file_type_display()
    ext = os.path.splitext(file_record.file.name)[1].lower()
    is_gutachter = (role == "gutachter")

    markdown = ""

    if file_record.is_pdf:
        text, num_pages = _extract_pdf_text(file_record.file)

        if _pdf_text_is_sufficient(text, num_pages):
            markdown = f"# {file_type_label}: {label}\n\n{text}"
        else:
            prompt = _get_doc_prompt(file_record.file_type, is_gutachter)
            markdown = _pdf_to_markdown_via_vision(file_record, prompt, label, file_type_label)

    elif file_record.is_image:
        if ext in CLAUDE_VISION_UNSUPPORTED:
            markdown = (
                f"[{file_type_label}: {label} — Format {ext} nicht unterstützt "
                f"(bitte als JPG/PNG hochladen)]"
            )
        else:
            if file_record.file_type == "photo":
                prompt = PHOTO_PROMPT_GUTACHTER if is_gutachter else PHOTO_PROMPT_MAKLER
            else:
                prompt = _get_doc_prompt(file_record.file_type, is_gutachter)
            markdown = _image_to_markdown(file_record, prompt, label, file_type_label)

    if not markdown:
        markdown = f"[{file_type_label}: {label} — konnte nicht verarbeitet werden]"

    file_record.markdown_content = markdown
    file_record.save(update_fields=["markdown_content"])
    return markdown


# ── Generierungs-Service ──────────────────────────────────────────────────────

class PropertyDescriptionService:
    def generate(self, report) -> str:
        import anthropic
        from .models import DescriptionTemplate

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        system = SYSTEM_PROMPT_GUTACHTER if report.role == "gutachter" else SYSTEM_PROMPT_MAKLER

        content = []

        # 1. Hardfacts
        facts = self._build_hardfacts(report)
        if facts:
            content.append({"type": "text", "text": f"## Objektdaten\n\n{facts}"})

        # 2. Referenz-Exposés / Vorlagen (max. 3, passender Gebäudetyp zuerst)
        from django.db.models import Case, IntegerField, When
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
                        f"## Referenz-Exposé: {tpl.name}"
                        + (f" [{tpl.get_building_type_display()}]" if tpl.building_type else "")
                        + (f" — {' '.join(filter(None, [tpl.street, tpl.postal_code, tpl.city]))}" if any([tpl.street, tpl.city]) else "")
                        + "\n\n"
                        + snippet + "\n\n"
                        + "[Analysiere dieses Referenz-Exposé: Bewertungslogik, Ausstattungsbewertung, "
                        + "Lagebeschreibung und Stil als Vorlage nutzen — kritisch prüfen und anpassen.]"
                    ),
                })

        # 3. Lazy Conversion: noch nicht verarbeitete Dateien jetzt aufbereiten
        pending = report.files.filter(markdown_content="").order_by("file_type", "uploaded_at")
        for f in pending:
            try:
                convert_file_to_markdown(f, role=report.role)
            except Exception as exc:
                logger.warning("Konvertierung übersprungen (%s): %s", f.filename, exc)

        # 4. Dokumente (Pläne, Bauakte, Sonstiges) vollständig einbeziehen
        doc_sections = []
        for f in report.files.exclude(file_type="photo").order_by("file_type", "uploaded_at"):
            mc = f.markdown_content
            if mc and not mc.startswith("["):
                doc_sections.append(mc[:MAX_FILE_MARKDOWN_CHARS])

        if doc_sections:
            content.append({
                "type": "text",
                "text": (
                    "## Grundrisse & Dokumente\n\n"
                    + "\n\n---\n\n".join(doc_sections)
                ),
            })

        # 5. Fotos: alle einbeziehen (wichtigstes Element), je 1.200 Zeichen
        photo_sections = []
        for f in report.files.filter(file_type="photo").order_by("uploaded_at"):
            mc = f.markdown_content
            if mc and not mc.startswith("["):
                photo_sections.append(mc[:MAX_PHOTO_MARKDOWN_CHARS])

        if photo_sections:
            content.append({
                "type": "text",
                "text": (
                    f"## Fotobeschreibungen ({len(photo_sections)} Fotos)\n\n"
                    "Die folgenden Beschreibungen wurden automatisch aus den hochgeladenen Fotos "
                    "generiert. Sie sind die primäre Informationsquelle für Zustand und Ausstattung.\n\n"
                    + "\n\n---\n\n".join(photo_sections)
                ),
            })

        # 6. Abschluss-Prompt
        if report.role == "gutachter":
            closing = (
                "Erstelle jetzt die Gutachter-Baubeschreibung (Verkehrswertgutachten-Stil) "
                "für dieses Objekt auf Basis aller bereitgestellten Informationen. "
                "Geh systematisch vor: Gebäude → Dach → Fassade → Fenster/Türen → "
                "Grundriss → Böden → Wände/Decken → Bäder → Heizung → Elektro → "
                "Modernisierungen → Gesamtzustand. Materialien und Zustand immer benennen."
            )
        else:
            addr_parts = list(filter(None, [report.street, report.postal_code, report.city]))
            addr = " ".join(addr_parts)
            closing = (
                "Erstelle jetzt die Makler-Objektbeschreibung (Exposé) "
                "in den drei Abschnitten: Immobilie, Ausstattung, Lage. "
            )
            if addr:
                closing += (
                    f"Für 'Lage' nutze dein Wissen über {addr} — beschreibe Infrastruktur, "
                    "ÖPNV, Schulen, Einkauf, Naherholung und Charakter des Viertels konkret."
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
        addr = " ".join(filter(None, [report.street, report.postal_code, report.city]))
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
