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
```

## Endpoints

```text
GET  /health
POST /invoices
GET  /documents/{document_id}
POST /workers/preprocess
POST /workers/ocr
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
FIRESTORE_DOCUMENT_COLLECTION=documents
FIRESTORE_DATABASE=(default)
```

If using a named Firestore database, set `FIRESTORE_DATABASE` to that database ID.

## Required Google Cloud Resources

- Cloud Storage bucket
- Firestore database
- Pub/Sub topic
- Pub/Sub push subscription
- Cloud Run service
- Vision API enabled

## Cloud Run Deploy

```bash
gcloud run deploy document-pipeline-api \
  --source . \
  --region europe-west3 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=your-project-id,GCS_UPLOAD_BUCKET=your-upload-bucket,PUBSUB_DOCUMENT_UPLOADED_TOPIC=document.uploaded,PUBSUB_OCR_REQUESTED_TOPIC=ocr.requested,FIRESTORE_DOCUMENT_COLLECTION=documents,FIRESTORE_DATABASE=your-firestore-database
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
  "status": "UPLOADED"
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
