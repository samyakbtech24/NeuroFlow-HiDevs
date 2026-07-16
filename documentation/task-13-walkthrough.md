# Walkthrough - Task 13: Security Hardening

The NeuroFlow RAG pipeline is now fully fortified against external attacks. We've successfully layered multiple security defenses to block unauthorized access, prevent XSS and SSRF, neutralize prompt injection attempts, and prevent accidental secret leaks!

## Changes Made

### 1. JWT Authentication Pipeline
- Implemented `create_access_token` and the `get_current_user` FastAPI dependency.
- Registered the `/auth/token` endpoint to vend scoped JSON Web Tokens.
- Embedded strict Role-Based Access Control (RBAC) globally into all routers. 
  - The Ingest Router mandates the `ingest` scope.
  - The Query Router mandates the `query` scope.
  - The Pipelines and Finetune Routers mandate the `admin` scope.
- **Result:** Without a valid Bearer token, the API will outright reject requests with a `401 Unauthorized` (excluding public paths like `/health` and `/metrics`).

### 2. Input Validation & Defense
- Engineered strict text sanitization using `bleach` to strip out malicious HTML and prevent stored XSS attacks.
- Enforced hard character limits to prevent memory-exhaustion payloads (5,000 for queries, 100 for pipeline names).
- Blocked Server-Side Request Forgery (SSRF) by validating URLs and rejecting `localhost` and private IP spaces (e.g., `192.168.x.x`).
- Validated raw file magic bytes to guarantee disguised Linux `ELF` or Windows `MZ` executables are instantly rejected, even if they have a `.pdf` extension!

### 3. Dual-Layer Prompt Injection Defense
- **Layer 1 (Pattern Matching):** Implemented high-speed regex pattern matching against known injection phrases (e.g., "ignore all previous instructions"). Embedded this directly into the background `worker.py` chunking loop to silently flag malicious intent in the vector database metadata.
- **Layer 2 (LLM Classifier):** Configured a fast, synchronous `gpt-4o-mini` classification call directly inside the `/query` endpoint. If a user query attempts to override instructions or exfiltrate data, the model catches it and the API blocks it instantly with a `400 Bad Request`.

### 4. Secret Redaction & Baseline Scanning
- Added regex scanning for AWS Access Keys, generic API Tokens, PEM headers, and JWTs right inside the background ingestion worker. 
- If a secret is spotted in a PDF, it is redacted (replaced with `[REDACTED]`) before generating vector embeddings, and securely logged.
- Generated the `.secrets.baseline` state file using `detect-secrets` to lock the codebase against accidental secret commits.

### 5. Security Response Headers
- Added a custom FastAPI middleware class to guarantee that every single HTTP response ships with robust security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY` (Clickjacking prevention)
  - `Strict-Transport-Security: max-age=31536000` (Enforcing HTTPS)
  - `Content-Security-Policy: default-src 'self'`
  - `X-Request-ID` (for deep tracing)

## Verification
- Authentication middleware successfully intercepts unauthorized requests.
- SSRF blocks attempts to reach internal IPs.
- Executables are rejected by the ingest API file parser.
- Secret baseline `.secrets.baseline` successfully committed.
