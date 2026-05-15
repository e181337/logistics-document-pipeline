import json
from datetime import datetime, timezone
from typing import Any

from app.gcp_clients import genai_client, settings
from app.repositories import DocumentRepository
from app.services.pubsub import PubSubMessageError, decode_pubsub_payload, require_value


TERMINAL_EXTRACTION_STATUSES = {"EXTRACTION_COMPLETED"}

BILL_OF_LADING_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "document_type": {"type": "STRING"},
        "bill_of_lading_number": {"type": "STRING", "nullable": True},
        "ship_from": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "nullable": True},
                "address": {"type": "STRING", "nullable": True},
                "city_state_zip": {"type": "STRING", "nullable": True},
                "sid": {"type": "STRING", "nullable": True},
            },
        },
        "ship_to": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "nullable": True},
                "address": {"type": "STRING", "nullable": True},
                "city_state_zip": {"type": "STRING", "nullable": True},
                "cid": {"type": "STRING", "nullable": True},
                "location_number": {"type": "STRING", "nullable": True},
            },
        },
        "third_party_bill_to": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "nullable": True},
                "address": {"type": "STRING", "nullable": True},
                "city_state_zip": {"type": "STRING", "nullable": True},
            },
        },
        "carrier": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING", "nullable": True},
                "trailer_number": {"type": "STRING", "nullable": True},
                "seal_number": {"type": "STRING", "nullable": True},
                "scac": {"type": "STRING", "nullable": True},
                "pro_number": {"type": "STRING", "nullable": True},
            },
        },
        "freight_terms": {"type": "STRING", "nullable": True},
        "total_weight": {"type": "STRING", "nullable": True},
        "package_count": {"type": "INTEGER", "nullable": True},
        "commodity_description": {"type": "STRING", "nullable": True},
        "nmfc_number": {"type": "STRING", "nullable": True},
        "freight_class": {"type": "STRING", "nullable": True},
        "special_instructions": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "shipper_signature_date": {"type": "STRING", "nullable": True},
        "carrier_signature_pickup_date": {"type": "STRING", "nullable": True},
    },
    "required": [
        "document_type",
        "bill_of_lading_number",
        "ship_from",
        "ship_to",
        "third_party_bill_to",
        "carrier",
        "freight_terms",
        "total_weight",
        "package_count",
        "commodity_description",
        "nmfc_number",
        "freight_class",
        "special_instructions",
        "shipper_signature_date",
        "carrier_signature_pickup_date",
    ],
}


class ExtractionService:
    def __init__(self) -> None:
        self.repository = DocumentRepository()
        self.genai = genai_client()

    def handle_pubsub_push(self, envelope: dict[str, Any]) -> dict[str, str]:
        payload = decode_pubsub_payload(envelope)
        document_id = require_value(payload, "document_id")

        document = self.repository.get(document_id)
        if document is None:
            raise PubSubMessageError(f"Document not found: {document_id}")

        if document.get("status") in TERMINAL_EXTRACTION_STATUSES:
            return {"document_id": document_id, "status": document["status"]}

        ocr = document.get("ocr")
        if not isinstance(ocr, dict) or not isinstance(ocr.get("text"), str):
            raise PubSubMessageError(f"OCR text not found for document: {document_id}")

        self.repository.update(
            document_id,
            {
                "status": "EXTRACTION_PROCESSING",
                "updated_at": datetime.now(timezone.utc),
            },
        )

        fields = self.extract_bill_of_lading_fields(ocr["text"])
        completed_at = datetime.now(timezone.utc)
        self.repository.update(
            document_id,
            {
                "status": "EXTRACTION_COMPLETED",
                "updated_at": completed_at,
                "extraction": {
                    "processed_at": completed_at,
                    "method": "llm_gemini_v1",
                    "model": settings().gemini_extraction_model,
                    "document_type": fields.get("document_type", "bill_of_lading"),
                    "fields": fields,
                },
            },
        )

        return {"document_id": document_id, "status": "EXTRACTION_COMPLETED"}

    def extract_bill_of_lading_fields(self, text: str) -> dict[str, Any]:
        prompt = build_extraction_prompt(text)
        response = self.genai.models.generate_content(
            model=settings().gemini_extraction_model,
            contents=prompt,
            config={
                "temperature": 0,
                "response_mime_type": "application/json",
                "response_schema": BILL_OF_LADING_SCHEMA,
            },
        )

        try:
            fields = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini extraction did not return valid JSON") from exc

        if not isinstance(fields, dict):
            raise RuntimeError("Gemini extraction response must be a JSON object")

        return fields


def build_extraction_prompt(text: str) -> str:
    return f"""
Extract structured fields from OCR text of a logistics Bill of Lading.

Follow the provided response schema exactly.
Use null for missing or uncertain scalar values.
Use an empty array for missing list values.
Do not invent values that are not supported by the OCR text.
Preserve identifiers, names, dates, and units exactly as they appear when possible.
For freight_terms, use one of: prepaid, collect, third_party, or null.

OCR text:
---
{text}
---
""".strip()
