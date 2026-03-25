from django.db import migrations, models

AGB_VORLAGE = """ALLGEMEINE GESCHÄFTSBEDINGUNGEN (AGB)
⚠ VORLAGE – Bitte durch einen Rechtsanwalt prüfen lassen und Platzhalter in [eckigen Klammern] ersetzen.

§ 1 Geltungsbereich
Diese Allgemeinen Geschäftsbedingungen gelten für alle Verträge, die zwischen [Firmenname] (nachfolgend „Auftragnehmer") und dem Auftraggeber über Leistungen in den Bereichen Immobilienvermittlung, Immobilienbewertung und Beratungsdienstleistungen geschlossen werden. Abweichende Bedingungen des Auftraggebers werden nur anerkannt, wenn der Auftragnehmer ihrer Geltung ausdrücklich schriftlich zugestimmt hat.

§ 2 Vertragsschluss
Der Vertrag kommt durch die schriftliche oder elektronische Auftragserteilung des Auftraggebers und die Auftragsbestätigung durch den Auftragnehmer zustande. Die Beauftragung gemäß dem beigefügten Angebot gilt als Auftragserteilung.

§ 3 Leistungen
3.1 Maklertätigkeit: Der Auftragnehmer erbringt Nachweis- und Vermittlungsleistungen für Kauf, Verkauf, Vermietung und Verpachtung von Immobilien.
3.2 Gutachten und Wertermittlung: Immobilienbewertungen werden nach anerkannten Verfahren (Vergleichswert-, Ertragswert-, Sachwertverfahren) auf Basis der zum Zeitpunkt der Erstellung vorliegenden Informationen erstellt.
3.3 Beratung: Der Auftragnehmer erbringt Beratungsleistungen im Bereich Immobilien, Kapitalanlagen und verwandter Gebiete.

§ 4 Vergütung und Zahlung
4.1 Die Vergütung ergibt sich aus dem jeweiligen Angebot bzw. der Auftragsbestätigung.
4.2 Rechnungen sind innerhalb von 14 Tagen ab Rechnungsdatum ohne Abzug zu begleichen, sofern nicht abweichend vereinbart.
4.3 Bei Zahlungsverzug werden Verzugszinsen in Höhe von 9 Prozentpunkten über dem Basiszinssatz (B2B) bzw. 5 Prozentpunkten über dem Basiszinssatz (B2C) berechnet.
4.4 Reservierungsgebühren werden bei Zustandekommen des Hauptvertrags auf die Maklerprovision angerechnet. Bei Rücktritt vom Kaufvertrag durch den Auftraggeber verfällt die Reservierungsgebühr.

§ 5 Stornierung und Rücktritt
5.1 Bei Stornierung durch den Auftraggeber vor Leistungsbeginn werden 20 % des vereinbarten Honorars als Aufwandspauschale fällig.
5.2 Bei Stornierung nach Leistungsbeginn wird das anteilig erbrachte Honorar zuzüglich entstandener Kosten fällig.
5.3 Gutachten, die nach Beauftragung und Ortstermin storniert werden, werden vollständig in Rechnung gestellt.

§ 6 Haftung
6.1 Der Auftragnehmer haftet für Schäden aus der Verletzung des Lebens, des Körpers oder der Gesundheit sowie für Schäden aus der Verletzung wesentlicher Vertragspflichten unbeschränkt.
6.2 Im Übrigen haftet der Auftragnehmer nur bei Vorsatz und grober Fahrlässigkeit.
6.3 Gutachten und Wertermittlungen basieren auf den zum Zeitpunkt der Erstellung verfügbaren Informationen und Marktdaten. Eine Haftung für Wertveränderungen nach Erstellung des Gutachtens ist ausgeschlossen.
6.4 Die Haftung für mittelbare Schäden, insbesondere entgangenen Gewinn, ist ausgeschlossen, soweit gesetzlich zulässig.

§ 7 Vertraulichkeit und Datenschutz
Alle im Rahmen der Geschäftsbeziehung übermittelten Daten und Informationen werden vertraulich behandelt. Die Verarbeitung personenbezogener Daten erfolgt gemäß der Datenschutz-Grundverordnung (DSGVO) und dem Bundesdatenschutzgesetz (BDSG). Näheres ergibt sich aus unserer Datenschutzerklärung unter [Website-URL].

§ 8 Urheberrecht
Gutachten, Bewertungsberichte und sonstige erstellte Unterlagen sind urheberrechtlich geschützt. Eine Weitergabe oder Veröffentlichung an Dritte bedarf der ausdrücklichen schriftlichen Zustimmung des Auftragnehmers.

§ 9 Schlussbestimmungen
9.1 Es gilt das Recht der Bundesrepublik Deutschland unter Ausschluss des UN-Kaufrechts.
9.2 Gerichtsstand für alle Streitigkeiten aus und im Zusammenhang mit diesem Vertrag ist, soweit gesetzlich zulässig, der Sitz des Auftragnehmers.
9.3 Sollten einzelne Bestimmungen dieser AGB unwirksam oder undurchführbar sein, bleibt die Wirksamkeit der übrigen Bestimmungen unberührt."""

WIDERRUFSBELEHRUNG_VORLAGE = """WIDERRUFSBELEHRUNG
⚠ VORLAGE – Gilt nur für Verbraucher (B2C). Bitte durch einen Rechtsanwalt prüfen lassen und Platzhalter in [eckigen Klammern] ersetzen.

Widerrufsrecht
Sie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu widerrufen.

Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des Vertragsschlusses.

Um Ihr Widerrufsrecht auszuüben, müssen Sie uns
[Firmenname], [Straße, PLZ, Stadt], [E-Mail], [Telefon]
mittels einer eindeutigen Erklärung (z. B. ein mit der Post versandter Brief oder eine E-Mail) über Ihren Entschluss, diesen Vertrag zu widerrufen, informieren. Zur Wahrung der Widerrufsfrist reicht es aus, dass Sie die Mitteilung über die Ausübung des Widerrufsrechts vor Ablauf der Widerrufsfrist absenden.

Widerrufsfolgen
Wenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen, die wir von Ihnen erhalten haben, unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag zurückzuzahlen, an dem die Mitteilung über Ihren Widerruf dieses Vertrags bei uns eingegangen ist.

Haben Sie verlangt, dass die Dienstleistungen während der Widerrufsfrist beginnen sollen, so haben Sie uns einen angemessenen Betrag zu zahlen, der dem Anteil der bis zu dem Zeitpunkt, zu dem Sie uns von der Ausübung des Widerrufsrechts unterrichten, bereits erbrachten Dienstleistungen im Vergleich zum Gesamtumfang der im Vertrag vorgesehenen Dienstleistungen entspricht.

Erlöschen des Widerrufsrechts
Das Widerrufsrecht erlischt bei einem Vertrag zur Erbringung von Dienstleistungen, wenn der Unternehmer die Dienstleistung vollständig erbracht hat und mit der Ausführung der Dienstleistung erst begonnen hat, nachdem der Verbraucher dazu seine ausdrückliche Zustimmung gegeben hat und gleichzeitig seine Kenntnis davon bestätigt hat, dass er sein Widerrufsrecht bei vollständiger Vertragserfüllung durch den Unternehmer verliert.

─────────────────────────────────────────────────
MUSTER-WIDERRUFSFORMULAR
(Wenn Sie den Vertrag widerrufen wollen, füllen Sie bitte dieses Formular aus und senden Sie es zurück.)

An: [Firmenname], [Adresse], [E-Mail]

Hiermit widerrufe(n) ich/wir (*) den von mir/uns (*) abgeschlossenen Vertrag über die Erbringung der folgenden Dienstleistung:
_______________________________________________

Bestellt am (*) / erhalten am (*): ________________

Name des/der Verbraucher(s): __________________

Anschrift des/der Verbraucher(s): ________________

Unterschrift (nur bei Mitteilung auf Papier): ________

Datum: _______________________________________

(*) Unzutreffendes streichen."""


def populate_legal_texts(apps, schema_editor):
    CompanySettings = apps.get_model("core", "CompanySettings")
    for cs in CompanySettings.objects.all():
        if not cs.agb_text:
            cs.agb_text = AGB_VORLAGE
        if not cs.widerrufsbelehrung_text:
            cs.widerrufsbelehrung_text = WIDERRUFSBELEHRUNG_VORLAGE
        cs.save(update_fields=["agb_text", "widerrufsbelehrung_text"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_remove_companysettings_pdf_footer_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="companysettings",
            name="agb_text",
            field=models.TextField(blank=True, verbose_name="AGB (Volltext)"),
        ),
        migrations.AddField(
            model_name="companysettings",
            name="widerrufsbelehrung_text",
            field=models.TextField(blank=True, verbose_name="Widerrufsbelehrung (Volltext)"),
        ),
        migrations.RunPython(populate_legal_texts, migrations.RunPython.noop),
    ]
