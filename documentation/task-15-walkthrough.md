# Walkthrough - Task 15: Production Containerization

NeuroFlow is now completely ready to be deployed to production. I have refactored our architecture to use secure, hardened, and highly-optimized Docker containers with a strict Nginx reverse proxy load balancer sitting at the edge!

## Changes Made

### 1. Multi-Stage Hardened Dockerfiles
- **Backend**: Implemented a two-stage `Dockerfile` (using `python:3.11-slim`) that separates the dependency build from the runtime. The runtime stage now drops root privileges by creating and switching to a `neuroflow` user. A `curl`-based `HEALTHCHECK` was integrated directly into the image to ensure Docker orchestrators automatically restart stalled APIs.
- **Frontend**: Implemented a multi-stage `node:20-slim` build. The Next.js app is compiled in the builder stage, and the standalone `server.js` artifacts are copied securely into a non-root runtime environment listening on port 3000.

### 2. Nginx Load Balancing & Security
- I generated self-signed SSL certificates (`nginx-selfsigned.key` and `nginx-selfsigned.crt`) inside `infra/nginx/certs` to enable secure HTTPS termination locally. 
- Created `infra/nginx/nginx.conf` containing:
  - An `upstream` block to **load-balance API traffic** across the two replicas.
  - Rate limiting restricted to **60 requests per minute**.
  - Strict security headers (`nosniff`, `DENY` clickjacking frames, and `Strict-Transport-Security`).
  - Native Gzip compression across all responses to reduce bandwidth!

### 3. Production Docker Compose (`docker-compose.prod.yml`)
- We dropped the massive development volume mounts in favor of immutable, compiled containers.
- The `api` and `worker` services are automatically scaled to **2 replicas** each.
- Applied extreme security parameters to the Python APIs:
  - `read_only: true` locks down the root filesystem.
  - `tmpfs: - /tmp` mounts a temporary RAM disk, which allows the app to process data without being able to write malicious scripts to disk.
  - `cap_drop: - ALL` strips all root-level Linux kernel capabilities (e.g., preventing raw socket creation).
  - Explicit CPU (`1.0` to `2.0`) and Memory (`1g` to `2g`) limits are strictly enforced.

## Verification
- Both Dockerfiles execute cleanly and drastically reduce the final image size (< 500MB).
- Executing `whoami` inside the API container returns `neuroflow`.
- Writing to the container filesystem throws `permission denied` (read-only enforcement successful).
