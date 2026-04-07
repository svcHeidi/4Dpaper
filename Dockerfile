# 4Dpapers - Containerized Scientific Paper Authoring
FROM python:3.11-slim

# Install system dependencies (Quarto, git, etc.)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Quarto
RUN curl -fsSL https://quarto.org/download/latest/quarto-linux-amd64.deb -o quarto.deb && \
    dpkg -i quarto.deb && \
    rm quarto.deb

# Create app directory (contains the 4Dpapers application code)
WORKDIR /app

# Copy application code (not the project - that comes via volume)
COPY dashboard /app/dashboard
COPY _extensions /app/_extensions
COPY serve.py /app/serve.py
COPY requirements.txt /app/requirements.txt 2>/dev/null || echo "# No requirements.txt yet" > /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir \
    panel>=1.3.0 \
    tornado>=6.3 \
    pyvista>=0.43.0 \
    quarto>=0.1.0

# Create project volume mount point
WORKDIR /workspace

# Expose default port
EXPOSE 5006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5006/api/health || exit 1

# Entry point: initialize project structure and start server
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["--port", "5006"]
