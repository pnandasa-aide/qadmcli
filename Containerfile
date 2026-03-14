# QADM CLI - AS400 DB2 for i Database Management Tool
# Containerfile for Podman/Docker

FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JT400_JAR=/opt/jt400/jt400.jar

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    openjdk-17-jre-headless \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Download jt400.jar
RUN mkdir -p /opt/jt400 && \
    curl -L -o /opt/jt400/jt400.jar \
    "https://sourceforge.net/projects/jt400/files/latest/download" || \
    echo "Please manually download jt400.jar from https://sourceforge.net/projects/jt400/"

# Copy requirements first for better caching
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -e .

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Reinstall in editable mode with source
RUN pip install -e .

# Create non-root user for security
RUN useradd -m -u 1000 qadmcli && \
    chown -R qadmcli:qadmcli /app

# Switch to non-root user
USER qadmcli

# Set entrypoint
ENTRYPOINT ["qadmcli"]
CMD ["--help"]
