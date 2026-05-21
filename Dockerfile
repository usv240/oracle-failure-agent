FROM python:3.11-slim

# Install Node.js 20 for MongoDB MCP server
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install MongoDB MCP server globally (pinned version for reproducibility)
RUN npm install -g mongodb-mcp-server@1.9.0

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create runtime directories
RUN mkdir -p outputs

# Non-root user for security
RUN useradd -m -u 1000 oracle && chown -R oracle:oracle /app
USER oracle

EXPOSE 8080

# Production server: 1 worker per CPU, keep-alive for Cloud Run
CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--timeout-keep-alive", "30", \
     "--log-level", "info"]
