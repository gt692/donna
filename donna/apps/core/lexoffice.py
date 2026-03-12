"""
apps/core/lexoffice.py

Lexoffice REST API v1 Client.

Jedes Unternehmen hat ein eigenes Lexoffice-Konto und damit einen eigenen API-Key.
Der Key wird über CompanyCredential.get_lexoffice_key(company) bezogen.

Ablauf beim Rechnungsstellen:
  1. create_invoice()  → erstellt finale Rechnung, liefert (invoice_id, voucher_number)
  2. get_invoice_pdf() → lädt das PDF herunter, liefert bytes

Fehlerbehandlung:
  - LexofficeError wird bei HTTP-Fehlern oder fehlenden Daten geworfen
  - Der Aufrufer fängt LexofficeError und bietet dem User einen Fallback (manueller PDF-Upload)
"""
from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Optional

import requests

logger = logging.getLogger(__name__)

LEXOFFICE_BASE_URL = "https://api.lexoffice.io/v1"


class LexofficeError(Exception):
    """Wird bei Fehlern in der Lexoffice-API geworfen."""


class LexofficeClient:
    """Schlanker Client für die Lexoffice REST API v1."""

    def __init__(self, api_key: str):
        if not api_key:
            raise LexofficeError("Kein Lexoffice API-Key konfiguriert.")
        self._api_key = api_key

    # ── Interne Hilfsmethoden ──────────────────────────────────────────────

    def _headers(self, accept: str = "application/json") -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": accept,
        }

    def _post(self, path: str, payload: dict, params: Optional[dict] = None) -> dict:
        url = f"{LEXOFFICE_BASE_URL}/{path}"
        try:
            resp = requests.post(
                url, json=payload, headers=self._headers(),
                params=params or {}, timeout=30,
            )
        except requests.RequestException as exc:
            raise LexofficeError(f"Netzwerkfehler: {exc}") from exc

        if resp.status_code not in (200, 201):
            raise LexofficeError(
                f"Lexoffice Fehler {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def _get_json(self, path: str) -> dict:
        url = f"{LEXOFFICE_BASE_URL}/{path}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
        except requests.RequestException as exc:
            raise LexofficeError(f"Netzwerkfehler: {exc}") from exc
        if resp.status_code != 200:
            raise LexofficeError(
                f"Lexoffice Fehler {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def _get_pdf(self, path: str) -> bytes:
        url = f"{LEXOFFICE_BASE_URL}/{path}"
        try:
            resp = requests.get(
                url, headers=self._headers(accept="application/pdf"), timeout=60,
            )
        except requests.RequestException as exc:
            raise LexofficeError(f"Netzwerkfehler beim PDF-Download: {exc}") from exc
        if resp.status_code != 200:
            raise LexofficeError(
                f"PDF-Download Fehler {resp.status_code}: {resp.text[:200]}"
            )
        return resp.content

    # ── Öffentliche API ────────────────────────────────────────────────────

    def create_invoice(
        self,
        customer_name: str,
        line_description: str,
        net_amount: Decimal,
        invoice_date: datetime.date,
        customer_lexoffice_id: Optional[str] = None,
        payment_term_days: int = 30,
    ) -> tuple[str, str]:
        """
        Erstellt eine finalisierte Rechnung in Lexoffice.

        Returns:
            (invoice_id, voucher_number)  — voucher_number kann leer sein wenn
            Lexoffice die Nummer noch nicht vergeben hat.
        """
        date_str = invoice_date.strftime("%Y-%m-%dT00:00:00.000+01:00")

        address: dict = {"name": customer_name}
        if customer_lexoffice_id:
            address["contactId"] = customer_lexoffice_id

        payload = {
            "voucherDate": date_str,
            "address": address,
            "lineItems": [
                {
                    "type": "custom",
                    "name": line_description,
                    "quantity": 1,
                    "unitName": "Pauschale",
                    "unitPrice": {
                        "currency": "EUR",
                        "netAmount": float(net_amount),
                        "taxRatePercentage": 19,
                    },
                    "discountPercentage": 0,
                }
            ],
            "totalPrice": {"currency": "EUR"},
            "taxConditions": {"taxType": "net"},
            "paymentConditions": {
                "paymentTermLabel": f"Zahlbar innerhalb {payment_term_days} Tagen netto",
                "paymentTermDuration": payment_term_days,
            },
            "shippingConditions": {
                "shippingDate": date_str,
                "shippingType": "none",
            },
        }

        result = self._post("invoices", payload, params={"finalize": "true"})
        invoice_id: str = result["id"]

        # Belegnummer aus dem Detail-Abruf holen
        voucher_number = ""
        try:
            detail = self._get_json(f"invoices/{invoice_id}")
            voucher_number = detail.get("voucherNumber", "")
        except LexofficeError:
            logger.warning("Konnte Belegnummer für Rechnung %s nicht abrufen.", invoice_id)

        return invoice_id, voucher_number

    def get_invoice_pdf(self, invoice_id: str) -> bytes:
        """Lädt das PDF einer finalisierten Rechnung herunter."""
        return self._get_pdf(f"invoices/{invoice_id}/document")


def get_client_for_company(company: str) -> LexofficeClient:
    """
    Baut einen LexofficeClient für das angegebene Unternehmen.
    Wirft LexofficeError wenn kein API-Key hinterlegt ist.
    """
    from apps.core.models import CompanyCredential
    api_key = CompanyCredential.get_lexoffice_key(company)
    return LexofficeClient(api_key)  # raises LexofficeError if key empty
