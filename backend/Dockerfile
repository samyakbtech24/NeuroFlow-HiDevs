FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential for C extensions like asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend code into /app/backend to preserve the package structure
COPY . ./backend

# Configure PYTHONPATH so the 'backend' package is discoverable
ENV PYTHONPATH=/app

# Create a wrapper script in the root /app to route 'python -m worker' to the package
RUN echo "import runpy; runpy.run_module('backend.worker', run_name='__main__')" > worker.py

# Expose FastAPI port
EXPOSE 8000

# Default command to run the FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
