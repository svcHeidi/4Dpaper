# 4Dpapers - Containerized Scientific Paper Authoring
FROM python:3.11-slim

# Version baked in at build time (passed by CI from the VERSION file)
ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="4Dpapers" \
      org.opencontainers.image.description="Browser-based IDE for interactive scientific papers" \
      org.opencontainers.image.version="$APP_VERSION" \
      org.opencontainers.image.source="https://github.com/svcHeidi/4Dpaper"

# Install system dependencies (Quarto, git, etc.)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ca-certificates \
    libgl1-mesa-dev \
    libegl1-mesa-dev \
    libgles2-mesa-dev \
    libosmesa6-dev \
    libglfw3-dev \
    xvfb \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install Quarto (architecture-aware)
RUN ARCH=$(dpkg --print-architecture) && \
    curl -fsSL "https://quarto.org/download/latest/quarto-linux-${ARCH}.deb" -o quarto.deb && \
    dpkg -i quarto.deb && \
    rm quarto.deb

# Create app directory (contains the 4Dpapers application code)
WORKDIR /app

# Install Python dependencies first (cached unless requirements.txt changes)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code (changes more frequently — after pip for cache efficiency)
COPY dashboard /app/dashboard
COPY _extensions /app/_extensions
COPY scripts /app/scripts
COPY serve.py /app/serve.py
COPY VERSION /app/VERSION
COPY _quarto-apphtml.yml /app/_quarto-apphtml.yml
COPY _quarto-paperview.yml /app/_quarto-paperview.yml
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Create project volume mount point
WORKDIR /workspace

# Expose default port
EXPOSE 5006

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5006/api/health || exit 1

# Entry point: initialize project structure and start server
ENTRYPOINT ["/app/docker-entrypoint.sh"]
