#!/usr/bin/env bash
#
# QADM CLI Container Helper Script for Bash
#
# Usage:
#   ./qadmcli.sh connection test
#   ./qadmcli.sh table list -l GSLIBTST
#   ./qadmcli.sh table convert -s config/schema/subscriber.yaml --source-db DB2 --target-db MSSQL
#

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env file
ENV_FILE="${SCRIPT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# Container configuration
IMAGE_NAME="qadmcli"
CONTAINER_NAME="qadmcli-${RANDOM}"

# Check if image exists
if ! podman images --format "{{.Repository}}" | grep -q "^localhost/${IMAGE_NAME}$"; then
    echo "🔨 Building qadmcli image..."
    podman build -t "$IMAGE_NAME" -f "${SCRIPT_DIR}/Containerfile" "$SCRIPT_DIR"
    if [ $? -ne 0 ]; then
        echo "❌ Build failed!"
        exit 1
    fi
    echo "✅ Build successful!"
else
    echo "📦 Using existing image: $IMAGE_NAME"
fi

# Run container
echo "🚀 Running: qadmcli $*"
podman run -it --rm --name "$CONTAINER_NAME" \
    -e AS400_USER="$AS400_USER" \
    -e AS400_PASSWORD="$AS400_PASSWORD" \
    -e MSSQL_USER="$MSSQL_USER" \
    -e MSSQL_PASSWORD="$MSSQL_PASSWORD" \
    -v "${SCRIPT_DIR}:/app:Z" \
    "$IMAGE_NAME" "$@"
