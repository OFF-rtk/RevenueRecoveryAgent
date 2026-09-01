# Phase 2: Detection Layer

## Overview

The Detection Layer is responsible for translating varying third-party (Razorpay) webhooks into a unified internal representation. By centralizing the parsing logic, the rest of the application only needs to deal with a consistent internal "Case" schema, isolating our core logic from upstream API shifts.

In this phase, we expanded our webhook handler to capture and normalize a range of critical revenue failure events into two primary categories: `failed_subscription` and `overdue_receivable`.

## What Was Built

### 1. Robust Payload Normalization
We implemented explicit logic within `core/webhooks/razorpay.py` to extract unified fields across distinct Razorpay webhook structures.
- **Event Mapping:** 
  - `payment.failed`, `subscription.pending`, and `subscription.halted` all map directly to the `failed_subscription` case type.
  - `invoice.expired` and `invoice.partially_paid` map directly to the `overdue_receivable` case type.
- **Field Extraction:** By leveraging functions like `_extract_amount()`, `_extract_customer_ref()`, and `_extract_failure_reason()`, we safely pull necessary details regardless of whether the event centers on a `payment`, `subscription`, or `invoice` entity. 

### 2. Graceful Error Handling
To prevent Razorpay from infinitely retrying webhooks we could never parse, we introduced a structured exception: `MalformedPayloadError`.
- **Safe Degradation:** If Razorpay sends an unexpected payload (e.g., missing critical IDs or entity blocks), our system throws a `MalformedPayloadError` rather than a generic 500 Internal Server Error.
- **API Response:** The `webhooks.py` router catches this error, logs a clear `"webhook_malformed_payload"` message, and safely returns an HTTP 200 `{"status": "ignored", "reason": "malformed payload"}` response. This confirms receipt to Razorpay and ceases retry attempts for fundamentally broken data.

### 3. Comprehensive Testing
We created `tests/test_phase2.py` utilizing our synchronous and asynchronous testing suites:
- **Event Accuracy:** Asserts that synthetic fixture payloads correctly translate to the appropriate `case_type` and store expected numerical values (e.g., 20000 paise stored as 200.00 INR).
- **Malformed Payloads:** Verifies that a structurally deficient payload logs the error and returns the `{"status": "ignored"}` 200 code without crashing the ingestion endpoint.
- **Pipeline Batch Validation:** Ran the unified pipeline against a batch of 10 alternating fixtures, confirming 100% success rate in translating diverse events into their normalized cases.

## Role in the Grand Scheme

This phase is critical because the core logic engine (Phase 3 & 4) *does not know* what a "Razorpay" is. The Recovery Agent operates purely on the abstract concepts of `failed_subscription` and `overdue_receivable`.

By building a robust Detection Layer in Phase 2, we guarantee that any upstream data messiness, varying error codes, or disparate payload structures are cleansed at the boundary. If we ever switch payment providers from Razorpay to Stripe, this layer is the *only* thing we need to change—the rest of our recovery logic remains intact.
