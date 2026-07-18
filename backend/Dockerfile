# Stage 1: Dependencies
FROM python:3.11-slim AS deps
WORKDIR /app
# Install curl for the healthcheck in the final stage (wait, it's better to install in runtime)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime (minimal, non-root)
FROM python:3.11-slim AS runtime

# Install curl for HEALTHCHECK
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

RUN groupadd -r neuroflow && useradd -r -g neuroflow neuroflow
WORKDIR /app

COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
COPY start.sh .

# Adjust ownership and make script executable
RUN chown -R neuroflow:neuroflow /app && \
    chmod +x start.sh

USER neuroflow

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Start both API and Worker concurrently via start.sh
CMD ["bash", "start.sh"]
