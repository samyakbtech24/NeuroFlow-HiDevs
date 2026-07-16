# Task 13: Security Hardening Implementation Plan

This plan covers the implementation of JWT Authentication, Input Validation, SSRF Protection, Prompt Injection defenses (Pattern + LLM), Secret Scanning, and Security Headers.

## Proposed Changes

### Setup & Infrastructure
- **Branch Strategy:** Checkout `task-12`, branch to `task-13`.
- **Dependencies:** Install `python-jose[cryptography]`, `bleach`, and `detect-secrets`.
- **Secret Baseline:** Run `detect-secrets scan --baseline .secrets.baseline` across the repository.

---

### Authentication (`backend/api/auth.py` & `backend/security/auth.py`)
- **[NEW]** Create `backend/security/auth.py` with JWT encoding/decoding utilities and a `get_current_user` FastAPI dependency.
- **[NEW]** Create `backend/api/auth.py` exposing `POST /auth/token` which accepts `client_id` and `client_secret` and returns a scoped JWT.
- **[MODIFY]** Update `backend/main.py` to register the auth router and enforce the JWT dependency globally (except for `/health` and `/metrics`).

---

### Input Validation & Sanitization (`backend/security/validators.py`)
- **[NEW]** Create `backend/security/validators.py`:
  - `sanitize_text()`: Uses `bleach.clean` to strip HTML.
  - `validate_url()`: Blocks private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) and `localhost` to prevent SSRF.
  - `validate_file_bytes()`: Checks file magic bytes against the provided MIME type to prevent malicious executable uploads disguised as PDFs.
- **[MODIFY]** Inject these validators into `backend/api/query.py` (max length 5000), `backend/api/pipelines.py` (max length 100), and `backend/api/ingest.py` (file validation & SSRF prevention).

---

### Prompt Injection Defense (`backend/security/prompt_injection.py`)
- **[NEW]** Create `backend/security/prompt_injection.py`:
  - `scan_patterns()`: Implements regex pattern matching for the provided `INJECTION_PATTERNS`.
  - `detect_llm_injection()`: Fires a fast LLM classification prompt to determine if the user query is attempting to override instructions.
- **[MODIFY]** `backend/api/query.py`: Run Layer 1 and Layer 2 on user queries. Reject with `400 Bad Request` if Layer 2 returns 'yes'.
- **[MODIFY]** `backend/worker.py`: Run Layer 1 on ingested document chunks and append `{"prompt_injection_detected": true}` to metadata if matched.

---

### Secret Scanning (`backend/security/secret_detector.py`)
- **[NEW]** Create `backend/security/secret_detector.py` containing regex patterns for AWS keys, API keys, PEM headers, and JWTs.
- **[MODIFY]** `backend/worker.py`: Before embedding, scan chunk text. If a secret is found, redact it to `[REDACTED]` and log the event.

---

### Security Middleware (`backend/main.py`)
- **[MODIFY]** Add a custom FastAPI middleware in `backend/main.py` that injects the required security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`, `Content-Security-Policy`, and a unique `X-Request-ID`.
