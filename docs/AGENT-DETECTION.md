# How Agent Detection and Auto-Start Works

## Overview

The `qadmcli.sh` script uses a **detect-then-auto-start** strategy:

1. Check if any agent is already running (3 methods, priority-ordered)
2. If no agent found, **auto-start** the agent as a persistent daemon container
3. Run the slim CLI container, which connects to the detected or auto-started agent

This is the default behavior for all users — no manual agent setup is required.

---

## Detection Priority

```
Method 1: $QADMCLI_AGENT_URL environment variable (Manual override)
    ↓ (if not set)
Method 2: Agent container running (podman ps → qadmcli-agent)
    ↓ (if not running)
Method 3: Host agent process (curl :8765/health returns 200)
    ↓ (if not found)
Auto-Start: Agent daemon container started automatically
    ↓
Run slim CLI container → command executes → agent stays running
```

---

## Method 1: Environment Variable (Manual Override)

**Priority:** Highest — checked first

**How it works:**
```bash
# Set custom agent URL (remote server, different port, etc.)
export QADMCLI_AGENT_URL=http://192.168.1.100:8765

# CLI uses this URL directly, no other detection attempted
./qadmcli.sh table list -l GSLIBTST
# Output: 🔌 Connected to Agent: http://192.168.1.100:8765
```

**Use case:** Agent running on a remote machine, different port, or custom configuration.

---

## Method 2: Agent Container

**Priority:** Second

**How it works:**
```bash
# Check if agent container is already running
podman ps --format '{{.Names}}' | grep "^qadmcli-agent$"
```

**Detection logic:**
```bash
if podman ps --format '{{.Names}}' 2>/dev/null | grep -q "^qadmcli-agent$"; then
    AGENT_URL="http://127.0.0.1:8765"
fi
```

**Use case:** Agent was previously auto-started by `qadmcli.sh` and is still running, or user started it manually.

---

## Method 3: Host Agent Process

**Priority:** Third

**How it works:**
```bash
# HTTP health check to localhost:8765
curl -s --max-time 2 http://127.0.0.1:8765/health
```

**Detection logic:**
```bash
if curl -s --max-time 2 http://127.0.0.1:8765/health > /dev/null 2>&1; then
    AGENT_URL="http://127.0.0.1:8765"
fi
```

**Use case:** Agent installed directly on the host (not containerized), or agent running in a different container type.

---

## Auto-Start: When No Agent Is Found

If all 3 detection methods fail, `qadmcli.sh` automatically starts the agent:

```bash
# Called by qadmcli.sh when detect_agent returns empty
default_start_agent() {
    # 1. Build agent image if missing
    ensure_image "qadmcli-agent" "Containerfile.agent"

    # 2. Remove any stale (stopped) container
    podman rm -f qadmcli-agent 2>/dev/null || true

    # 3. Start agent as persistent daemon
    podman run -d --name qadmcli-agent \
        --network=host \
        -e AS400_HOST="$AS400_HOST" \
        -e AS400_USER="$AS400_USER" \
        -e AS400_PASSWORD="$AS400_PASSWORD" \
        qadmcli-agent agent start --foreground

    # 4. Wait for health check (up to 15 seconds)
    for i in $(seq 1 15); do
        if curl -s --max-time 1 http://127.0.0.1:8765/health > /dev/null; then
            echo "✅ Agent daemon is healthy and ready"
            return 0
        fi
        sleep 1
    done

    # 5. Failed to start — show logs
    echo "❌ Agent failed to start within 15s"
    podman logs qadmcli-agent | tail -20
    return 1
}
```

**The agent container continues running after the CLI command completes.** Subsequent CLI invocations find it via Method 2 and skip the auto-start.

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────┐
│  User runs: ./qadmcli.sh <command>      │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Step 1: Ensure CLI image built         │
│  podman build -t qadmcli-cli ...        │
│  (cached after first build)             │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Step 2: Detect running agent           │
│                                         │
│  ┌─ $QADMCLI_AGENT_URL set? ──→ USE IT │
│  ├─ podman ps → agent container? → USE │
│  ├─ curl :8765/health → host agent? USE│
│  └─ No agent found ──→ Auto-Start      │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Step 3: Auto-start (if needed)         │
│                                         │
│  ├─ Build agent image if missing        │
│  ├─ podman run -d qadmcli-agent         │
│  └─ Wait for health check (max 15s)     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Step 4: Run slim CLI container         │
│  podman run --rm qadmcli-cli <command>  │
│  QADMCLI_AGENT_URL=http://127.0.0.1:8765│
│                                         │
│  CLI → HTTP POST /sql/batch → Agent     │
│  Agent → JVM → JT400 → AS400            │
│  Results → JSON → CLI prints → exits    │
└─────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  Step 5: Agent persists                 │
│  Agent container stays running          │
│  Ready for next command (no delay)      │
└─────────────────────────────────────────┘
```

---

## Detecting Agent vs Running CLI

| Scenario | Detection Result | CLI Container Used |
|---|---|---|
| First run (cold start) | No agent → auto-start | `qadmcli-cli` (builds first) |
| Subsequent runs | Method 2: container found | `qadmcli-cli` (cached) |
| Host agent pre-started | Method 3: curl OK | `qadmcli-cli` |
| Manual override set | Method 1: env var | `qadmcli-cli` |
| Agent container stopped | No agent → auto-start | `qadmcli-cli` (agent rebuilds) |

---

## Build Commands

Two separate images must be built. `qadmcli.sh` builds them automatically on first use:

```bash
# These are called automatically by qadmcli.sh — manual build is optional:
podman build -t qadmcli-cli -f Containerfile.cli .      # ~180MB
podman build -t qadmcli-agent -f Containerfile.agent .    # ~692MB
```

To force a rebuild:
```bash
podman rmi qadmcli-cli qadmcli-agent  # Remove cached images
./qadmcli.sh table list               # Rebuilds on next run
```

---

## Troubleshooting

### Agent not starting?

```bash
# Check if agent container exists (stopped or running)
podman ps -a | grep qadmcli-agent

# Remove stale container and let auto-start recreate it
podman rm -f qadmcli-agent
./qadmcli.sh connection check  # auto-starts agent again

# View agent logs for errors
podman logs qadmcli-agent

# Check AS400 credentials
export QADMCLI_DEBUG=1
./qadmcli.sh connection check
```

### Force specific detection mode?

```bash
# Force agent URL (bypasses all detection)
export QADMCLI_AGENT_URL=http://127.0.0.1:8765
./qadmcli.sh table list

# Prevent auto-start (agent not started)
# Stop any running agent first:
podman stop qadmcli-agent
# Then run (will fail if no agent found — use for testing detection)
./qadmcli.sh connection check
```

### Agent is running but CLI can't connect?

```bash
# Check if agent is healthy
curl http://127.0.0.1:8765/health

# Check agent is listening on correct interface
# Must use --network=host for the agent container
podman inspect qadmcli-agent --format '{{.HostConfig.NetworkMode}}'
# Should output: "host"
```

---

## Summary

- **Auto-detection** checks 3 methods in priority order: env var → container → host process
- **Auto-start** creates the agent container if no agent is found (new default behavior)
- **Auto-recovery** — if agent container stops, next CLI invocation restarts it
- **Two images** — `qadmcli-cli` (~180MB) and `qadmcli-agent` (~692MB), both auto-built
- **Zero configuration** needed — just run `./qadmcli.sh <command>` and it works
