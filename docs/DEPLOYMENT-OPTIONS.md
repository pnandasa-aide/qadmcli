# QADMCLI Deployment Options

## Overview

QADMCLI now uses a **split-container architecture** with two images:

| Image | Size | Contents | Purpose |
|---|---|---|---|
| `qadmcli-cli` (default) | ~180MB | Pure Python (click, rich, requests) | Per-command CLI, fast startup |
| `qadmcli-agent` | ~692MB | JVM + JT400 + ODBC + connection pool | Persistent daemon for DB work |

The **`qadmcli.sh` script auto-detects the agent and auto-starts it** if not running. No manual agent setup needed.

Supported deployment modes:

1. **Direct CLI Mode** (Development) - CLI runs directly on host, no containers
2. **Hybrid Mode** - Agent on host + CLI in container
3. **Agent Container Mode** - Agent and CLI in separate containers (manual)
4. **Auto-Start Agent Mode** (Default, Recommended) - Agent auto-starts via `qadmcli.sh`

---

## Option 1: Direct CLI Mode (Development)

**CLI runs directly on the host. No containers involved.**

Use this for development, debugging, or when container runtime is not available. Requires all dependencies installed on the host.

### Architecture:

```
┌────────────────────────────────────┐
│  Host Machine                      │
│                                    │
│  ┌──────────────────────────────┐  │
│  │  qadmcli CLI (host process)  │  │
│  │  - Python 3.11+              │  │
│  │  - click, rich, requests     │  │
│  │  - Optional: JRE 17 + JT400  │  │
│  │  - Optional: FastAPI + uvico  │  │
│  │  - Direct or agent connect   │  │
│  └──────────────┬───────────────┘  │
│                 │                   │
│                 │ JT400 / HTTP      │
└─────────────────┼───────────────────┘
                   │
                   ▼
           ┌──────────────┐
           │ AS400 Server │
           │161.82.146.249│
           └──────────────┘
```

### Pros:
- ✅ No container startup overhead
- ✅ Fast for single commands
- ✅ Easy debugging (can add print/logging)
- ✅ No Podman/Docker needed

### Cons:
- ❌ Requires Python 3.10+ on host
- ❌ Agent requires JRE 17 + JT400 installed
- ❌ Manual dependency management
- ❌ Not isolated from host environment

### Commands & Steps:

```bash
# Step 1: Install CLI (core only)
cd /home/ubuntu/_qoder/qadmcli
pip install -e .

# Step 2: (Optional) Install agent dependencies
pip install -e .[agent]

# Step 3: Set environment variables
export AS400_HOST=161.82.146.249
export AS400_USER=your_username
export AS400_PASSWORD=your_password

# Step 4: Run commands directly
qadmcli connection test
qadmcli table list -l GSLIBTST
qadmcli mockup generate -t THAI_TEST -l GSLIBTST -r 100

# Step 5: (Optional) Start agent for faster bulk operations
qadmcli agent start
qadmcli mockup generate -t THAI_TEST -l GSLIBTST -r 1000
# Uses agent automatically (20x faster)
```

---

## Option 2: Hybrid Mode (Recommended for Performance)

**Agent on HOST (persistent JVM) + CLI in CONTAINER**

### Architecture:

```
┌──────────────────────────────────────────────────┐
│  Host Machine (Ubuntu)                            │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │  Podman Container (per command)          │    │
│  │  ┌────────────────────────────────────┐  │    │
│  │  │  qadmcli CLI                       │  │    │
│  │  │  - No JVM, No JT400                │  │    │
│  │  │  - Sends HTTP requests to agent    │  │    │
│  │  │  - Receives results                │  │    │
│  │  └──────────────┬─────────────────────┘  │    │
│  │                 │ HTTP API               │    │
│  └─────────────────┼────────────────────────┘    │
│                    │ localhost:8765              │
│                    │                             │
│  ┌─────────────────▼────────────────────────┐    │
│  │  AS400 Agent Daemon (Persistent)         │    │
│  │  ┌────────────────────────────────────┐  │    │
│  │  │  JVM (running 24/7)                │  │    │
│  │  │  - JT400 library loaded            │  │    │
│  │  │  - Connection pool (5 connections) │  │    │
│  │  │  - REST API on port 8765           │  │    │
│  │  └────────────────────────────────────┘  │    │
│  └─────────────────┬────────────────────────┘    │
│                    │ JT400 Connection            │
└────────────────────┼─────────────────────────────┘
                     │
                     ▼
            ┌──────────────┐
            │ AS400 Server │
            │161.82.146.249│
            └──────────────┘
```

**Flow:**
1. CLI container starts (~3s)
2. CLI detects agent on localhost:8765
3. CLI sends HTTP requests to agent (bulk operations)
4. Agent executes via persistent JVM + JT400 connection pool
5. CLI container exits (~1s cleanup)
6. Agent keeps running for next command

### Pros:
- ✅ **20x faster** bulk operations (~200 rows/sec)
- ✅ Persistent JVM (no startup overhead per command)
- ✅ Connection pooling (5 pre-created connections)
- ✅ CLI still isolated in container
- ✅ Best of both worlds

### Cons:
- ⚠️ Requires host Python for agent
- ⚠️ Agent must be started separately (runs in background)

### Commands & Steps:

#### Phase 1: One-Time Setup

```bash
# Step 1: Install agent dependencies on HOST
cd /home/ubuntu/_qoder/qadmcli
pip install -e .[agent]

# Step 2: Set environment variables (add to ~/.bashrc for persistence)
export AS400_HOST=161.82.146.249
export AS400_USER=your_username
export AS400_PASSWORD=your_password
export AS400_LIBRARY=GSLIBTST  # Optional
```

#### Phase 2: Start Agent (Once, Runs Forever)

```bash
# Step 3: Start agent daemon on HOST
qadmcli agent start

# Expected output:
# 🚀 Starting AS400 Agent...
#    Config: /home/ubuntu/.qadmcli/agent.json
#    Log: /home/ubuntu/.qadmcli/agent.log
#    PID: 12345
#    Waiting for agent to start...
#    ... (5s)
# ✅ Agent started successfully!
#    URL: http://127.0.0.1:8765
#    Health: http://127.0.0.1:8765/health
#    Status: http://127.0.0.1:8765/status

# Step 4: Verify agent is running
qadmcli agent status

# Expected output:
# ✅ Agent is running (PID: 12345)
# 📊 Agent Status:
#    Version: 0.1.0
#    JVM: running
#    JT400: loaded
#    Uptime: 0h 2m
# 🔌 Connection Pool:
#    Size: 5
#    Active: 0
#    Idle: 5
#    Total Queries: 0
```

#### Phase 3: Use CLI (Containerized, Auto-Detects Agent)

```bash
# Step 5: Run CLI commands normally
./qadmcli.sh connection test
./qadmcli.sh table list -l GSLIBTST
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000 --batch-size 500

# Expected output:
# 🔌 Detected agent on host: http://127.0.0.1:8765
# 🚀 Running: qadmcli mockup generate -t THAI_TEST -l GSLIBTST -r 1000 --batch-size 500
#
# Using AS400 agent (bulk mode)
# Inserted: 500 rows in 2.1s (238 rows/sec)
# Updated: 300 rows in 1.2s (250 rows/sec)

# Performance: ~200 rows/sec (20x faster than pure container!)
```

#### Phase 4: Stop Agent (When Done for the Day)

```bash
# Step 6: Stop agent daemon
qadmcli agent stop

# Expected output:
# 🛑 Stopping agent (PID: 12345)...
# ✅ Agent stopped

# Or view agent logs
qadmcli agent logs
tail -f ~/.qadmcli/agent.log
```

---

## Option 3: Agent in Container

**Agent and CLI each run in SEPARATE containers**

### Architecture:

```
┌──────────────────────────────────────────────────┐
│  Host Machine (Ubuntu)                            │
│                                                   │
│  ┌──────────────────────────────────────────┐    │
│  │  Container 2: CLI (per command)          │    │
│  │  ┌────────────────────────────────────┐  │    │
│  │  │  qadmcli CLI                       │  │    │
│  │  │  - No JVM, No JT400                │  │    │
│  │  │  - Sends HTTP requests to agent    │  │    │
│  │  │  - Receives results                │  │    │
│  │  └──────────────┬─────────────────────┘  │    │
│  │                 │ HTTP API               │    │
│  └─────────────────┼────────────────────────┘    │
│                    │ localhost:8765              │
│                    │                             │
│  ┌─────────────────▼────────────────────────┐    │
│  │  Container 1: Agent (Persistent)         │    │
│  │  ┌────────────────────────────────────┐  │    │
│  │  │  JVM (running 24/7)                │  │    │
│  │  │  - JT400 library loaded            │  │    │
│  │  │  - Connection pool (5 connections) │  │    │
│  │  │  - Direct connection to AS400      │  │    │
│  │  └────────────────────────────────────┘  │    │
│  └─────────────────┬────────────────────────┘    │
│                    │ JT400 Connection            │
└────────────────────┼─────────────────────────────┘
                     │
                     ▼
            ┌──────────────┐
            │ AS400 Server │
            │161.82.146.249│
            └──────────────┘
```

**Flow:**
1. Agent container starts once and runs persistently
2. CLI container starts per command (~3s)
3. CLI detects agent container on localhost:8765
4. CLI sends HTTP requests to agent container
5. Agent container executes via its JVM + JT400
6. CLI container exits, agent container keeps running

### Pros:
- ✅ **17x faster** bulk operations (~167 rows/sec)
- ✅ Persistent JVM (no startup overhead per command)
- ✅ Connection pooling
- ✅ Full container isolation (no host Python needed)
- ✅ Managed entirely via podman

### Cons:
- ⚠️ Slightly slower than hybrid (container networking overhead)
- ⚠️ Agent container must be managed separately

### Commands & Steps:

#### Phase 1: Build Image (One-Time)

```bash
# Step 1: Build agent image
cd /home/ubuntu/_qoder/qadmcli
sudo podman build -t qadmcli-agent -f Containerfile.agent .
```

#### Phase 2: Start Agent Container (Once, Runs Forever)

```bash
# Step 2: Set environment variables
export AS400_HOST=161.82.146.249
export AS400_USER=your_username
export AS400_PASSWORD=your_password

# Step 3: Start agent as persistent container
sudo podman run -d \
  --name qadmcli-agent \
  --network=host \
  -e AS400_HOST=$AS400_HOST \
  -e AS400_USER=$AS400_USER \
  -e AS400_PASSWORD=$AS400_PASSWORD \
  qadmcli agent start

# Expected output: (container ID)

# Step 4: Verify agent container is running
sudo podman ps | grep qadmcli-agent

# Expected output:
# CONTAINER ID   IMAGE     COMMAND           STATUS
# abc123         qadmcli   "agent start"     Up 2 minutes

# Step 5: Check agent health
sudo podman exec qadmcli-agent curl -s http://localhost:8765/health | jq

# Expected output:
# {
#   "status": "healthy",
#   "jvm_running": true,
#   "jt400_version": "JT400 loaded (JVM running)",
#   "uptime_seconds": 120.5
# }
```

#### Phase 3: Use CLI Container (Auto-Detects Agent)

```bash
# Step 6: Run CLI commands
./qadmcli.sh connection test
./qadmcli.sh table list -l GSLIBTST
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000 --batch-size 500

# Expected output:
# 🔌 Detected agent on host: http://127.0.0.1:8765
# 🚀 Running: qadmcli mockup generate ...
#
# Using AS400 agent (bulk mode)
# Inserted: 500 rows in 2.5s (200 rows/sec)
# Updated: 300 rows in 1.5s (200 rows/sec)

# Performance: ~167 rows/sec (slightly slower than hybrid due to container networking)
```

#### Phase 4: Manage Agent Container

```bash
# View agent logs
sudo podman logs -f qadmcli-agent

# Restart agent container
sudo podman restart qadmcli-agent

# Stop agent container
sudo podman stop qadmcli-agent

# Remove agent container
sudo podman rm qadmcli-agent

# Check agent status (if running)
sudo podman exec qadmcli-agent curl -s http://localhost:8765/status | jq
```


---

## Option 4: Auto-Start Agent Mode (Default, Recommended)

**Agent auto-starts and runs in a container. CLI runs in a slim container.**

This is the **new default** for `qadmcli.sh`. No manual setup required.

### Architecture:

```
$ ./qadmcli.sh table list -l GSLIBTST
       |
       v
  detect_agent()
       |
       +-- Found running?
       |       |
       |       v
       |   launch slim CLI container (qadmcli-cli, ~150MB)
       |       |
       |       v
       |   CLI sends HTTP to agent:8765 --> agent executes via JVM --> CLI exits
       |
       +-- Not found?
               |
               v
           auto-start agent daemon (qadmcli-agent, persistent)
               |
               v
           wait for health check (up to 15s)
               |
               v
           launch slim CLI container --> command executes --> CLI exits
               |
               v
           agent stays running for next call
```

### Container Layout:

```
Host
  |-- Container: qadmcli-cli (per command, --rm)  ~180MB, starts in <1s
  |     - Pure Python CLI (click, rich, requests)
  |     - No JVM, no JT400, no ODBC
  |     - Communicates with agent via HTTP REST API
  |
  |-- Container: qadmcli-agent (daemon, persistent)  ~692MB
        - JVM 24/7, JT400 pool, ODBC drivers
        - REST API on :8765
        - Auto-started on first use, stays running
```

### Benefits:

- **No manual agent setup** - auto-starts on first command
- **Fast per-command startup** - slim CLI container starts in <1s
- **No JVM overhead** - agent has persistent JVM
- **No host dependencies** - everything in containers
- **Agent stays running** - subsequent commands use existing agent

### Commands:

```bash
# Just run any command -- agent auto-starts if needed
./qadmcli.sh connection test
./qadmcli.sh table list -l GSLIBTST
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000

# Stop agent when done
podman stop qadmcli-agent

# Build images manually (optional)
podman build -t qadmcli-cli -f Containerfile.cli .
podman build -t qadmcli-agent -f Containerfile.agent .
```

---

## Performance Comparison

| Mode | Startup | 100 rows | 1000 rows | Throughput |
|------|---------|----------|-----------|------------|
| **Pure Container** | 4-6s | ~10s | ~100s | 10 rows/sec |
| **Hybrid (Agent)** | 0s | ~0.8s | ~5s | **200 rows/sec** |
| **Auto-Start Agent** | 0s (first: ~15s) | ~0.8s | ~5s | **200 rows/sec** |
| **Agent Container** | 0s | ~1s | ~6s | 167 rows/sec |

---

## Environment Variables

### Agent Configuration:

| Variable | Description | Default |
|----------|-------------|---------|
| `AS400_HOST` | AS400 server address | `161.82.146.249` |
| `AS400_USER` | AS400 username | - |
| `AS400_PASSWORD` | AS400 password | - |
| `AS400_LIBRARY` | Default library | `*LIBL` |
| `QADMCLI_AGENT_URL` | Agent URL (auto-detected) | `http://127.0.0.1:8765` |

### Agent Options:

| Option | Description | Default |
|--------|-------------|---------|
| `--host` | Agent bind address | `127.0.0.1` |
| `--port` | Agent port | `8765` |
| `--jt400-path` | Path to jt400.jar | `/opt/jt400/jt400.jar` |
| `--pool-size` | Connection pool size | `5` |

---

## Auto-Start Agent (Systemd Service)

For production, run agent as systemd service:

```bash
sudo nano /etc/systemd/system/qadmcli-agent.service
```

``ini
[Unit]
Description=QADMCLI AS400 Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/_qoder/qadmcli
Environment=AS400_HOST=161.82.146.249
EnvironmentFile=/home/ubuntu/_qoder/.env
ExecStart=/home/ubuntu/_qoder/qadmcli/venv/bin/python3 -m qadmcli_agent.cli start
ExecStop=/home/ubuntu/_qoder/qadmcli/venv/bin/python3 -m qadmcli_agent.cli stop
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable qadmcli-agent
sudo systemctl start qadmcli-agent

# Check status
sudo systemctl status qadmcli-agent

# View logs
sudo journalctl -u qadmcli-agent -f
```

---

## Migration Guide

### From Direct CLI (Host) to Auto-Start Agent:

```bash
# 1. Install agent dependencies
pip install -e .[agent]

# 2. Start agent
qadmcli agent start

# 3. Verify agent is running
qadmcli agent status

# 4. Use CLI normally (auto-detects agent)
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000

# 5. Enjoy 20x performance! 🚀
```

### Revert to Direct Mode:

```bash
# Unset agent URL
unset QADMCLI_AGENT_URL

# Stop agent container
podman stop qadmcli-agent

# Use CLI directly (host mode)
qadmcli mockup generate -t THAI_TEST -l GSLIBTST -r 100
```

---

## Which Option Should I Use?

### Use **Direct CLI** (Development) if:
- You're developing or debugging the CLI
- You want to iterate quickly on code
- You have Python 3.10+ available on host
- Container runtime is not available

### Use **Auto-Start Agent (Default)** if:
- ✅ You just want to run commands (recommended for all users)
- ✅ You want the best performance with zero setup
- ✅ You want everything in containers (no host deps)
- ✅ This is the default — just run `./qadmcli.sh`

### Use **Hybrid Mode** if:
- You want persistent JVM but prefer agent on host
- You already have JRE + JT400 installed on host
- You want to avoid the container image build for agent

---

## Troubleshooting

### Agent not detected by container

```bash
# Check agent is running
qadmcli agent status

# Check port is accessible
curl http://127.0.0.1:8765/health

# Restart agent
qadmcli agent stop
qadmcli agent start

# Check agent logs
qadmcli agent logs
```

### Container can't reach host agent

```bash
# Use --network=host for container
sudo podman run --network=host ...

# Or use host IP instead of 127.0.0.1
export QADMCLI_AGENT_URL=http://192.168.1.100:8765
```

### JT400 not found

```bash
# Find JT400 location
find /opt -name "jt400.jar" 2>/dev/null

# Specify path
qadmcli agent start --jt400-path /path/to/jt400.jar
```

---

## Summary

- **Default behavior**: `./qadmcli.sh` auto-starts agent + runs slim CLI container
- **Zero setup required**: `.env` file is all you need
- **Agent auto-start**: Agent container is created on first use, stays running
- **Two container images**: `qadmcli-cli` (~180MB) and `qadmcli-agent` (~692MB)
- **No workflow changes**: Same CLI commands as before, zero code changes needed


