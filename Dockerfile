# Multi-stage build to optimize image size
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/config

# Copy dependencies from builder
COPY --from=builder /root/.local /root/.local

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY config/*.example ./config/

# Expose port
EXPOSE 8080

# Start command
CMD ["python", "-m", "src.main"]
