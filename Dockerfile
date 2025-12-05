# Chatbot Tester - Docker Image
# Multi-stage build for smaller final image

# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 2: Runtime with Playwright
# ============================================
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY run.py .
COPY src/ ./src/
COPY wizard/ ./wizard/
COPY config/ ./config/

# Create directories for runtime data
RUN mkdir -p /app/projects /app/reports

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default to headless mode in Docker
ENV CHATBOT_TESTER_HEADLESS=true

# Volume mounts for persistent data
VOLUME ["/app/projects", "/app/reports", "/app/config"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python run.py --health-check || exit 1

# Entry point
ENTRYPOINT ["python", "run.py"]

# Default command (can be overridden)
CMD ["--help"]
