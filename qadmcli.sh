#!/usr/bin/env bash
#
# QADM CLI - Unified Container Wrapper with Agent Auto-Detection and Auto-Start
#
# Usage:
#   ./qadmcli.sh connection check
#   ./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 100
#
# Flow:
#   1. Detect running agent (env var > container > host process)
#   2. If no agent found, auto-start agent daemon container
#   3. Launch slim CLI container that connects to agent via REST API
#

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Determine if output should be suppressed (JSON or summary format)
if [[ "$*" == *"--format json"* ]] || [[ "$*" == *"--format summary"* ]]; then
    SUPPRESS_OUTPUT=true
else
    SUPPRESS_OUTPUT=false
fi

# Container configuration
CLI_IMAGE="qadmcli-cli"
CLI_CONTAINERFILE="Containerfile.cli"
AGENT_IMAGE="qadmcli-agent"
AGENT_CONTAINERFILE="Containerfile.agent"
AGENT_CONTAINER_NAME="qadmcli-agent"
AGENT_PORT=8765

# Try to find and load .env file
ENV_FILE=""
if [ -f "${SCRIPT_DIR}/.env" ]; then
    ENV_FILE="${SCRIPT_DIR}/.env"
elif [ -f "${SCRIPT_DIR}/../.env" ]; then
    ENV_FILE="${SCRIPT_DIR}/../.env"
fi

if [ -n "$ENV_FILE" ]; then
    # Only print loading message if not requesting formatted output
    if [[ "$*" != *"--format json"* ]] && [[ "$*" != *"--format summary"* ]]; then
        echo -e "${BLUE}📄 Loading environment from $ENV_FILE...${NC}"
    fi
    # Read .env file and export variables
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip comments and empty lines
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue
        
        # Export variable
        export "$line"
    done < "$ENV_FILE"
fi

# Build image if missing
ensure_image() {
    local name="$1"
    local containerfile="$2"
    if ! podman images --format "{{.Repository}}" | grep -q "^localhost/${name}$"; then
        if [ "$SUPPRESS_OUTPUT" = false ]; then
            echo -e "${BLUE}🔨 Building ${name} image...${NC}"
        fi
        podman build -t "$name" -f "${SCRIPT_DIR}/${containerfile}" "$SCRIPT_DIR"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ Build of ${name} failed!${NC}" >&2
            exit 1
        fi
        if [ "$SUPPRESS_OUTPUT" = false ]; then
            echo -e "${GREEN}✅ Build of ${name} successful!${NC}"
        fi
    fi
}

# Detect if agent is running (host or container)
detect_agent() {
    # Method 1: Check if agent environment variable is set
    if [ -n "$QADMCLI_AGENT_URL" ]; then
        echo "$QADMCLI_AGENT_URL"
        return 0
    fi
    
    # Method 2: Check if agent container is running
    if podman ps --format '{{.Names}}' 2>/dev/null | grep -q "^${AGENT_CONTAINER_NAME}$"; then
        echo "http://127.0.0.1:${AGENT_PORT}"
        return 0
    fi
    
    # Method 3: Check if agent is running on host
    if command -v curl &> /dev/null; then
        if curl -s --max-time 2 http://127.0.0.1:${AGENT_PORT}/health > /dev/null 2>&1; then
            echo "http://127.0.0.1:${AGENT_PORT}"
            return 0
        fi
    fi
    
    # No agent found
    return 1
}

# Auto-start the agent as a persistent daemon container
default_start_agent() {
    if [ "$SUPPRESS_OUTPUT" = false ]; then
        echo -e "${BLUE}🔧 No running agent detected. Starting agent daemon...${NC}"
    fi
    
    # Build agent image if missing
    ensure_image "$AGENT_IMAGE" "$AGENT_CONTAINERFILE"
    
    # Remove stale container if it exists (not running)
    podman rm -f "$AGENT_CONTAINER_NAME" 2>/dev/null || true
    
    # Start agent container as a daemon
    podman run -d --name "$AGENT_CONTAINER_NAME" \
        --network=host \
        --userns=keep-id \
        -e AS400_HOST="$AS400_HOST" \
        -e AS400_USER="$AS400_USER" \
        -e AS400_PASSWORD="$AS400_PASSWORD" \
        -e AS400_LIBRARY="${AS400_LIBRARY:-*LIBL}" \
        -e MSSQL_HOST="$MSSQL_HOST" \
        -e MSSQL_USER="$MSSQL_USER" \
        -e MSSQL_PASSWORD="$MSSQL_PASSWORD" \
        -e QADMCLI_DEBUG="$QADMCLI_DEBUG" \
        "$AGENT_IMAGE" agent start --foreground
    
    # Wait for agent to become healthy (up to 15 seconds)
    local max_retries=15
    local retry=0
    while [ $retry -lt $max_retries ]; do
        if curl -s --max-time 1 http://127.0.0.1:${AGENT_PORT}/health > /dev/null 2>&1; then
            if [ "$SUPPRESS_OUTPUT" = false ]; then
                echo -e "${GREEN}✅ Agent daemon is healthy and ready${NC}"
            fi
            return 0
        fi
        sleep 1
        retry=$((retry + 1))
    done
    
    echo -e "${RED}❌ Agent failed to start within ${max_retries}s${NC}" >&2
    podman logs "$AGENT_CONTAINER_NAME" 2>/dev/null | tail -20 || true
    return 1
}

# Ensure CLI image is built
ensure_image "$CLI_IMAGE" "$CLI_CONTAINERFILE"

# Detect agent, auto-start if needed
AGENT_URL=$(detect_agent || echo "")
if [ -z "$AGENT_URL" ]; then
    default_start_agent
    AGENT_URL="http://127.0.0.1:${AGENT_PORT}"
fi

if [[ "$*" != *"--format json"* ]] && [[ "$*" != *"--format summary"* ]]; then
    echo -e "${GREEN}🔌 Connected to Agent: $AGENT_URL${NC}"
fi

# Run CLI container (slim image, no JVM/ODBC needed)
PODMAN_ARGS=(
    -it --rm --name "cli-$$"
    --network=host
    --userns=keep-id
    -e AS400_HOST="$AS400_HOST"
    -e AS400_USER="$AS400_USER"
    -e AS400_PASSWORD="$AS400_PASSWORD"
    -e AS400_LIBRARY="${AS400_LIBRARY:-*LIBL}"
    -e MSSQL_HOST="$MSSQL_HOST"
    -e MSSQL_USER="$MSSQL_USER"
    -e MSSQL_PASSWORD="$MSSQL_PASSWORD"
    -e QADMCLI_DEBUG="$QADMCLI_DEBUG"
    -e QADMCLI_AGENT_URL="$AGENT_URL"
    -v "${SCRIPT_DIR}:/app:Z"
)

if [[ "$*" == *"--format json"* ]] || [[ "$*" == *"--format summary"* ]]; then
    podman run "${PODMAN_ARGS[@]}" "$CLI_IMAGE" "$@"
else
    echo -e "${BLUE}🚀 Running: qadmcli $*${NC}\n"
    podman run "${PODMAN_ARGS[@]}" "$CLI_IMAGE" "$@"
fi
