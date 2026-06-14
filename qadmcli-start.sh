#!/usr/bin/env bash
# qadmcli-start.sh - Start the QADMCLI Agent as a background daemon container
#
# Usage:
#   ./qadmcli-start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Try to find and load .env file
ENV_FILE=""
if [ -f "${SCRIPT_DIR}/.env" ]; then
    ENV_FILE="${SCRIPT_DIR}/.env"
elif [ -f "${SCRIPT_DIR}/../.env" ]; then
    ENV_FILE="${SCRIPT_DIR}/../.env"
fi

if [ -n "$ENV_FILE" ]; then
    echo -e "${BLUE}📄 Loading environment from $ENV_FILE...${NC}"
    # Read .env file and export variables
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip comments and empty lines
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        
        # Export variable
        export "$line"
    done < "$ENV_FILE"
    echo -e "${GREEN}✅ Environment loaded${NC}"
else
    echo -e "${RED}⚠️  Warning: .env file not found. Running with host shell environment variables only.${NC}"
fi

# Validate required variables
if [ -z "$AS400_USER" ]; then
    echo -e "${RED}❌ Error: AS400_USER is not configured in the environment or .env${NC}"
    exit 1
fi

if [ -z "$AS400_PASSWORD" ]; then
    echo -e "${RED}❌ Error: AS400_PASSWORD is not configured in the environment or .env${NC}"
    exit 1
fi

IMAGE_NAME="qadmcli-agent"
CONTAINER_NAME="qadmcli-agent"

# Stop and remove any existing agent container
if sudo podman ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${BLUE}Stopping and removing existing ${CONTAINER_NAME} container...${NC}"
    sudo podman stop "$CONTAINER_NAME" &>/dev/null || true
    sudo podman rm "$CONTAINER_NAME" &>/dev/null || true
fi

# Run container in background
echo -e "${BLUE}🚀 Starting ${CONTAINER_NAME} in the background...${NC}"
sudo podman run -d \
    --name "$CONTAINER_NAME" \
    --network=host \
    -e AS400_HOST="${AS400_HOST:-161.82.146.249}" \
    -e AS400_USER="$AS400_USER" \
    -e AS400_PASSWORD="$AS400_PASSWORD" \
    -e MSSQL_HOST="$MSSQL_HOST" \
    -e MSSQL_USER="$MSSQL_USER" \
    -e MSSQL_PASSWORD="$MSSQL_PASSWORD" \
    -e QADMCLI_DEBUG="${QADMCLI_DEBUG:-}" \
    -v "${SCRIPT_DIR}:/app:Z" \
    "$IMAGE_NAME" agent start --foreground

echo -e "${GREEN}✅ Agent started successfully in background!${NC}"
echo -e "${BLUE}   Logs: sudo podman logs -f ${CONTAINER_NAME}${NC}"
