# GCP Document Processing Lab

Small learning project for an async document-processing pipeline on Google Cloud.

## Current Scope

- Upload an invoice image/PDF through an API.
- Store the file in Cloud Storage.
- Create a document state record in Firestore.
- Publish a `document.uploaded` event to Pub/Sub.
- Process the Pub/Sub message with a Cloud Run worker endpoint.
- Update Firestore status from `UPLOADED` to `PREPROCESSED`.
- Extract basic preprocess metadata such as image width, height, format, and page count.
- Publish an `ocr.requested` event after preprocess.
- Run OCR with Google Cloud Vision and store extracted text in Firestore.
- Publish an `extraction.requested` event after OCR.
- Extract Bill of Lading fields from OCR text with Gemini structured JSON output and store them in Firestore.
- Publish a `validation.requested` event after extraction.
- Run deterministic validation rules and route documents to completed or review states.
- Create a Firestore review task when validation returns warnings or errors.
- Resolve review tasks and mark the source document as `REVIEW_COMPLETED`.
- Track per-document workflow state across upload, preprocess, OCR, extraction, validation, and review.

## Architecture

```text
POST /invoices
  -> Cloud Storage
  -> Firestore document record
  -> Pub/Sub topic: document.uploaded
  -> Push subscription
  -> POST /workers/preprocess
  -> Firestore status: PREPROCESSED
  -> Pub/Sub topic: ocr.requested
  -> Push subscription
  -> POST /workers/ocr
  -> Firestore status: OCR_COMPLETED
  -> Pub/Sub topic: extraction.requested
  -> Push subscription
  -> POST /workers/extract
  -> Firestore status: EXTRACTION_COMPLETED
  -> Pub/Sub topic: validation.requested
  -> Push subscription
  -> POST /workers/validate
  -> Firestore status: VALIDATION_COMPLETED | VALIDATION_COMPLETED_WITH_WARNINGS | NEEDS_REVIEW
  -> Firestore review_tasks record when review is required
  -> POST /review-tasks/{review_task_id}/resolve
  -> Firestore status: REVIEW_COMPLETED
```

## Endpoints

```text
GET  /health
POST /invoices
GET  /documents/{document_id}
GET  /review-tasks/{review_task_id}
POST /review-tasks/{review_task_id}/resolve
POST /workers/preprocess
POST /workers/ocr
POST /workers/extract
POST /workers/validate
```

Worker endpoints expect the standard Pub/Sub push payload shape.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Authenticate with Google Cloud:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Create `.env` from the example:

```bash
cp .env.example .env
```

Run the API:

```bash
python -m uvicorn app.main:app --reload
```

Upload a sample invoice:

```bash
curl -X POST http://127.0.0.1:8000/invoices \
  -F "file=@/path/to/invoice.pdf" \
  -F "tenant_id=demo-tenant"
```

Read the document state:

```bash
curl http://127.0.0.1:8000/documents/doc_YOUR_DOCUMENT_ID
```

## Environment

Create `.env`:

```env
GCP_PROJECT_ID=your-project-id
GCS_UPLOAD_BUCKET=your-upload-bucket
PUBSUB_DOCUMENT_UPLOADED_TOPIC=document.uploaded
PUBSUB_OCR_REQUESTED_TOPIC=ocr.requested
PUBSUB_EXTRACTION_REQUESTED_TOPIC=extraction.requested
PUBSUB_VALIDATION_REQUESTED_TOPIC=validation.requested
FIRESTORE_DOCUMENT_COLLECTION=documents
FIRESTORE_REVIEW_TASK_COLLECTION=review_tasks
FIRESTORE_DATABASE=(default)
VERTEX_AI_LOCATION=global
GEMINI_EXTRACTION_MODEL=gemini-2.5-flash
```

If using a named Firestore database, set `FIRESTORE_DATABASE` to that database ID.

## Required Google Cloud Resources

- Cloud Storage bucket
- Firestore database
- Pub/Sub topic
- Pub/Sub push subscription
- Cloud Run service
- Vision API enabled
- Vertex AI / Gemini API enabled

## Cloud Run Deploy

```bash
gcloud run deploy document-pipeline-api \
  --source . \
  --region europe-west3 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=your-project-id,GCS_UPLOAD_BUCKET=your-upload-bucket,PUBSUB_DOCUMENT_UPLOADED_TOPIC=document.uploaded,PUBSUB_OCR_REQUESTED_TOPIC=ocr.requested,PUBSUB_EXTRACTION_REQUESTED_TOPIC=extraction.requested,PUBSUB_VALIDATION_REQUESTED_TOPIC=validation.requested,FIRESTORE_DOCUMENT_COLLECTION=documents,FIRESTORE_REVIEW_TASK_COLLECTION=review_tasks,FIRESTORE_DATABASE=your-firestore-database,VERTEX_AI_LOCATION=global,GEMINI_EXTRACTION_MODEL=gemini-2.5-flash
```

After deployment, create Pub/Sub push subscriptions:

```text
Topic: document.uploaded
Subscription ID: preprocess-worker-sub
Delivery type: Push
Endpoint URL: https://YOUR_CLOUD_RUN_URL/workers/preprocess

Topic: ocr.requested
Subscription ID: ocr-worker-sub
Delivery type: Push
Endpoint URL: https://YOUR_CLOUD_RUN_URL/workers/ocr

Topic: extraction.requested
Subscription ID: extraction-worker-sub
Delivery type: Push
Endpoint URL: https://YOUR_CLOUD_RUN_URL/workers/extract

Topic: validation.requested
Subscription ID: validation-worker-sub
Delivery type: Push
Endpoint URL: https://YOUR_CLOUD_RUN_URL/workers/validate
```

## Dead Letter Queue Setup

Create one dead-letter topic and one pull subscription per worker:

```bash
gcloud pubsub topics create preprocess.dead-letter
gcloud pubsub topics create ocr.dead-letter
gcloud pubsub topics create extraction.dead-letter
gcloud pubsub topics create validation.dead-letter

gcloud pubsub subscriptions create preprocess-dead-letter-sub --topic=preprocess.dead-letter
gcloud pubsub subscriptions create ocr-dead-letter-sub --topic=ocr.dead-letter
gcloud pubsub subscriptions create extraction-dead-letter-sub --topic=extraction.dead-letter
gcloud pubsub subscriptions create validation-dead-letter-sub --topic=validation.dead-letter
```

Grant the Pub/Sub service account permission to publish failed messages to dead-letter topics:

```bash
PROJECT_ID=your-project-id
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
PUBSUB_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding preprocess.dead-letter \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher"

gcloud pubsub topics add-iam-policy-binding ocr.dead-letter \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher"

gcloud pubsub topics add-iam-policy-binding extraction.dead-letter \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher"

gcloud pubsub topics add-iam-policy-binding validation.dead-letter \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.publisher"
```

Grant the same service account permission on the original worker subscriptions:

```bash
gcloud pubsub subscriptions add-iam-policy-binding preprocess-worker-sub \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.subscriber"

gcloud pubsub subscriptions add-iam-policy-binding ocr-worker-sub \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.subscriber"

gcloud pubsub subscriptions add-iam-policy-binding extraction-worker-sub \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.subscriber"

gcloud pubsub subscriptions add-iam-policy-binding validation-worker-sub \
  --member="serviceAccount:${PUBSUB_SERVICE_ACCOUNT}" \
  --role="roles/pubsub.subscriber"
```

Enable dead lettering on the worker subscriptions:

```bash
gcloud pubsub subscriptions update preprocess-worker-sub \
  --dead-letter-topic=preprocess.dead-letter \
  --max-delivery-attempts=5

gcloud pubsub subscriptions update ocr-worker-sub \
  --dead-letter-topic=ocr.dead-letter \
  --max-delivery-attempts=5

gcloud pubsub subscriptions update extraction-worker-sub \
  --dead-letter-topic=extraction.dead-letter \
  --max-delivery-attempts=5

gcloud pubsub subscriptions update validation-worker-sub \
  --dead-letter-topic=validation.dead-letter \
  --max-delivery-attempts=5
```

When a worker fails, the API still returns a non-2xx response so Pub/Sub can retry. The document workflow also records the failed step:

```json
{
  "status": "OCR_FAILED",
  "workflow": {
    "current_step": "ocr",
    "status": "failed",
    "steps": {
      "ocr": {
        "status": "failed",
        "last_error": "..."
      }
    }
  }
}
```

## Sample Document

Generate a filled Bill of Lading sample from the local template:

```bash
python scripts/fill_sample_bol.py
```

Output:

```text
samples/filled_bill_of_lading.png
```

## Expected Document State

After upload:

```json
{
  "status": "UPLOADED",
  "workflow": {
    "current_step": "preprocess",
    "status": "running",
    "steps": {
      "upload": {
        "status": "completed"
      },
      "preprocess": {
        "status": "pending"
      }
    }
  }
}
```

After Pub/Sub triggers preprocess:

```json
{
  "status": "PREPROCESSED",
  "preprocess": {
    "document_kind": "image",
    "image_width": 1932,
    "image_height": 2500,
    "image_format": "PNG",
    "page_count": 1
  }
}
```

After Pub/Sub triggers OCR:

```json
{
  "status": "OCR_COMPLETED",
  "ocr": {
    "provider": "google_cloud_vision",
    "text": "BILL OF LADING...",
    "text_length": 1234
  }
}
```

After Pub/Sub triggers extraction:

```json
{
  "status": "EXTRACTION_COMPLETED",
  "extraction": {
    "method": "llm_gemini_v1",
    "model": "gemini-2.5-flash",
    "document_type": "bill_of_lading",
    "fields": {
      "bill_of_lading_number": "BOL-2026-0515-0007",
      "ship_from": {
        "name": "Anatolia Export GmbH"
      },
      "ship_to": {
        "name": "Bosphorus Retail A.S."
      },
      "carrier": {
        "name": "Rhine Freight Logistics"
      },
      "total_weight": "2,520 kg"
    }
  }
}
```

After Pub/Sub triggers validation:

```json
{
  "status": "VALIDATION_COMPLETED_WITH_WARNINGS",
  "workflow": {
    "current_step": "review",
    "status": "waiting",
    "steps": {
      "validation": {
        "status": "completed"
      },
      "review": {
        "status": "waiting",
        "review_task_id": "review_abc123"
      }
    }
  },
  "validation": {
    "method": "deterministic_rules_v1",
    "review_task_id": "review_abc123",
    "issue_count": 2,
    "issues": [
      {
        "field": "ship_to.city_state_zip",
        "severity": "warning",
        "code": "postal_code_missing_or_suspicious"
      }
    ]
  }
}
```

Review task:

```json
{
  "review_task_id": "review_abc123",
  "document_id": "doc_abc123",
  "status": "OPEN",
  "priority": "normal",
  "reason": "validation_issues",
  "issues": []
}
```

Resolve review task:

```bash
curl -X POST http://127.0.0.1:8000/review-tasks/review_abc123/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "resolution": "APPROVED_WITH_WARNINGS",
    "reviewed_by": "operator@example.com",
    "notes": "Postal code warnings accepted for this shipment."
  }'
```

Valid resolutions:

```text
APPROVED
APPROVED_WITH_WARNINGS
CORRECTED
REJECTED
```

After review resolution:

```json
{
  "status": "REVIEW_COMPLETED",
  "workflow": {
    "current_step": "review",
    "status": "completed",
    "steps": {
      "review": {
        "status": "completed"
      }
    }
  }
}
```
