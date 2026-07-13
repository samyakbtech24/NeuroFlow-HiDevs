FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential for C extensions, tesseract for OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and pipelines code
COPY backend ./backend
COPY pipelines ./pipelines

# Configure PYTHONPATH so the packages are discoverable
ENV PYTHONPATH=/app

# Create a wrapper script in the root /app to route 'python -m worker' to the package
RUN echo "import runpy; runpy.run_module('backend.worker', run_name='__main__')" > worker.py

# Expose FastAPI port
EXPOSE 8000

# Default command to run the FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
