# QADMCLI Agent Architecture

## Overview

QADMCLI uses a **split-container client-agent architecture** that separates the lightweight CLI from all heavy database machinery. Instead of loading JVM + JT400 + ODBC per command (which added 8-12s overhead in the monolithic approach), the system runs a persistent agent daemon that handles all database operations, while a slim CLI container executes each command in under 1 second.

The architecture relies on three key techniques:

- **Lazy imports** at the Python module level so the CLI can import all packages without loading JVM/ODBC libraries
- **Optional dependency groups** in `pyproject.toml` to keep the CLI image minimal (~180MB vs ~692MB agent)
- **Health-check protocol with auto-start logic** in the shell wrapper — the agent auto-starts on first use

---

## Design Architecture

### Container Layout

```
Host Machine
  |
  |-- [qadmcli.sh] detects or auto-starts agent
  |     |
  |     +-- Container: qadmcli-cli (per command, --rm)
  |     |     ~180MB | Python 3.11-slim | No JVM, No JT400, No ODBC
  |     |     Core: click, rich, requests, pydantic, pyyaml
  |     |     ──────────────────────────────────────────────
  |     |     Sends HTTP REST requests to agent API on :8765
  |     |     Receives results as JSON
  |     |     Exits when command completes
  |     |
  |     +-- Container: qadmcli-agent (daemon, persistent)
  |           ~692MB | Python 3.11 + JRE 17
  |           System: JRE 17, msodbcsql18, unixodbc-dev
  |           Python: jpype, jaydebeapi, fastapi, uvicorn
  |                    pyodbc, pymysql, oracledb
  |           ──────────────────────────────────────────────
  |           FastAPI REST server on port 8765
  |           JT400 connection pool (persistent JVM)
  |           Auto-started on first use, stays running for subsequent commands
  |
  +-- AS400 Server (remote, e.g. 161.82.146.249)
        JT400 JDBC connections from agent pool
```

### Auto-Start Flow

```
$ ./qadmcli.sh table list -l GSLIBTST
       │
       ├── [ensure_image] Build CLI image if missing (Containerfile.cli)
       │
       ├── [detect_agent] Check for running agent
       │     ├── $QADMCLI_AGENT_URL set?          → use it directly
       │     ├── podman ps → qadmcli-agent running? → use it
       │     ├── curl :8765/health → host agent?    → use it
       │     └── none found                         → auto-start agent
       │
       ├── [default_start_agent] Auto-start agent daemon
       │     ├── Build agent image if missing (Containerfile.agent)
       │     ├── podman rm -f qadmcli-agent (remove stale)
       │     ├── podman run -d --network=host qadmcli-agent agent start --foreground
       │     └── Wait up to 15s for /health → OK
       │
       └── Run slim CLI container
             ├── podman run --rm qadmcli-cli "$@"
             ├── QADMCLI_AGENT_URL=http://127.0.0.1:8765
             └── CLI sends REST requests → agent executes → CLI exits
```

---

## Component Breakdown

### 1. Slim CLI Client (`qadmcli-cli`)

**Purpose:** Stateless CLI that sends commands to agent via HTTP REST. Pure Python, no system dependencies.

| Aspect | Detail |
|---|---|
| **Containerfile** | `Containerfile.cli` |
| **Source** | `src/qadmcli/` |
| **Size** | ~180 MB |
| **Base image** | `python:3.11-slim-bookworm` |
| **Entrypoint** | `qadmcli` |
| **Python deps** | click, rich, requests, pydantic, pydantic-settings, pyyaml |

**Execution behavior:**

1. Python process starts (< 1s container startup)
2. Click parses command-line args
3. `AS400AgentClient` reads `QADMCLI_AGENT_URL` env var and checks health
4. For mockup batch operations: sends `HTTP POST /sql/batch` to agent
5. For direct queries: connects via JT400 (lazy imports, but JRE must be present)
6. Process exits, container removed (`--rm`)

**Key source files:**

- [`agent_client.py`](src/qadmcli/db/agent_client.py) — HTTP client for agent REST API
- [`mockup.py`](src/qadmcli/db/mockup.py) — routes bulk INSERT/UPDATE/DELETE to agent when available
- [`connection.py`](src/qadmcli/db/connection.py) — lazy-imports jpype/jaydebeapi only when JT400 path is needed
- [`cli.py`](src/qadmcli/cli.py) — click-based CLI entry point
- [`agent_commands.py`](src/qadmcli/cli_commands/agent_commands.py) — registers agent sub-commands from `qadmcli_agent` package

### 2. Agent Daemon (`qadmcli-agent`)

**Purpose:** Persistent process that hosts JVM, JT400 connection pool, FastAPI REST server, and bulk operation engine.

| Aspect | Detail |
|---|---|
| **Containerfile** | `Containerfile.agent` |
| **Source** | `qadmcli_agent/` |
| **Size** | ~692 MB |
| **Base image** | `python:3.11-slim-bookworm` |
| **System deps** | `openjdk-17-jre-headless`, `unixodbc-dev`, `msodbcsql18`, `curl`, `ca-certificates` |
| **Python deps** | jpype1, jaydebeapi, fastapi, uvicorn, pyodbc, pymysql, oracledb + all CLI deps |
| **JT400** | `/opt/jt400/jt400.jar` (from `lib/jt400.jar`) |

**Startup sequence:**

1. JVM starts via jpype (`JVMManager`, ~2-3s, once)
2. JT400 connection pool initializes (`ConnectionPool`, 5 connections, ~1-2s)
3. FastAPI server listens on port 8765
4. `/health` endpoint responds `{"status": "healthy"}`
5. Agent stays running for subsequent commands

**Key source files:**

- [`server.py`](qadmcli_agent/server.py) — FastAPI app with REST endpoints (`/health`, `/status`, `/sql/execute`, `/sql/batch`, `/mockup/generate`)
- [`connection_pool.py`](qadmcli_agent/connection_pool.py) — JT400 connection pool with `Queue`, health checks, auto-reconnect
- [`jvm_manager.py`](qadmcli_agent/jvm_manager.py) — JVM lifecycle (start/stop/restart)
- [`cli.py`](qadmcli_agent/cli.py) — `agent start/stop/status` CLI commands
- [`mockup.py`](qadmcli_agent/mockup.py) — bulk mockup operations via JDBC batch API

**REST API endpoints:**

| Endpoint | Method | Purpose | Used by |
|---|---|---|---|
| `/health` | GET | Health check | `qadmcli.sh` detection, auto-start wait |
| `/status` | GET | Detailed agent status | `qadmcli agent status` |
| `/sql/execute` | POST | Execute single SQL | CLI direct queries |
| `/sql/batch` | POST | Batch SQL execution (bulk) | CLI mockup generation |
| `/mockup/generate` | POST | Full mockup generation | CLI mockup via agent |

### 3. Shell Wrapper (`qadmcli.sh`)

**Purpose:** Auto-detect or auto-start agent, then run slim CLI container.

**Key functions:**

| Function | Purpose |
|---|---|
| `ensure_image(name, containerfile)` | Build container image if not already present |
| `detect_agent()` | Check 3 methods: env var → container → host curl |
| `default_start_agent()` | Build agent image, start daemon, wait for health (max 15s) |

**Detection priority:**

```
1. $QADMCLI_AGENT_URL env var (manual override)
2. podman ps → qadmcli-agent container running
3. curl http://127.0.0.1:8765/health (host agent process)
4. None found → auto-start agent daemon (default_start_agent)
```

---

## Software Stack

### CLI Image

| Layer | Component | Purpose |
|---|---|---|
| Base | `python:3.11-slim-bookworm` | Minimal Python runtime |
| Core deps | `click>=8.1.0` | CLI argument parsing |
| | `rich>=13.0.0` | Formatted terminal output |
| | `requests>=2.31.0` | HTTP client for agent API |
| | `pydantic>=2.0.0`, `pydantic-settings>=2.0.0` | Configuration validation |
| | `pyyaml>=6.0` | YAML schema parsing |

**Total size: ~180 MB** (pure Python, no system packages beyond base image)

### Agent Image

| Layer | Component | Purpose |
|---|---|---|
| Base | `python:3.11-slim-bookworm` | Python runtime |
| System | `openjdk-17-jre-headless` | JVM for JT400 JDBC driver |
| | `unixodbc-dev`, `msodbcsql18` | Microsoft ODBC 18 for MSSQL |
| | `curl`, `ca-certificates` | ODBC install, health checks |
| | `gcc`, `g++` | Build tools for Python native extensions |
| Python | `jpype1>=1.4.0` | Python-Java bridge for JT400 |
| | `jaydebeapi>=1.2.3` | JDBC database API for Python |
| | `fastapi>=0.104.0`, `uvicorn>=0.24.0` | REST API server |
| | `pyodbc>=4.0.39` | MSSQL ODBC driver |
| | `pymysql>=1.1.0` | MySQL driver |
| | `oracledb>=2.0.0` | Oracle driver |
| JT400 | `/opt/jt400/jt400.jar` | IBM Toolbox for Java JDBC driver |

**Total size: ~692 MB** (includes JRE, ODBC, JT400, and all Python packages)

### Dependency Separation

`pyproject.toml` separates agent-specific packages into an optional dependency group:

```toml
# Core deps — installed in BOTH CLI and Agent images
dependencies = [
    "click>=8.1.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "rich>=13.0.0",
]

# Agent-only deps — installed ONLY in Agent image
[project.optional-dependencies]
agent = [
    "jpype1>=1.4.0",
    "jaydebeapi>=1.2.3",
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "pyodbc>=4.0.39",
    "pymysql>=1.1.0",
    "oracledb>=2.0.0",
]
```

CLI image installs: `pip install -e .` (core only)
Agent image installs: `pip install -e .[agent]` (core + agent)

---

## Techniques in Use

### 1. Lazy Imports

The CLI image has no JRE or ODBC installed. To allow all Python packages to be imported without triggering `ImportError`, heavy database driver imports are deferred from module-level to inside the specific methods that actually use them.

**`connection.py`** — JT400/JVM imports deferred:

```python
class AS400ConnectionManager:
    def _start_jvm(self) -> None:
        import jpype  # ← loaded only when JVM is needed
        if not jpype.isJVMStarted():
            jpype.startJVM(jpype.getDefaultJVMPath(), classpath=[jt400_path])

    def connect(self) -> None:
        self._start_jvm()
        import jaydebeapi  # ← loaded only for actual DB connection
        self._connection = jaydebeapi.connect(...)
```

**`mssql.py`** — pyodbc import deferred + `from __future__ import annotations`:

```python
from __future__ import annotations  # PEP 563: deferred type evaluation

class MSSQLConnection:
    def connect(self) -> None:
        import pyodbc  # ← loaded only for MSSQL operations
        ...
```

**`oracle.py`** — oracledb import deferred (same pattern):

```python
from __future__ import annotations

class OracleConnection:
    def connect(self) -> None:
        import oracledb  # ← loaded only for Oracle operations
        ...
```

### 2. PEP 563 Future Annotations (`from __future__ import annotations`)

Files that use lazy imports for the DB driver also use this import to defer type annotation evaluation. This allows type hints that reference driver types (e.g., `pyodbc.Connection`, `oracledb.Connection`) in class signatures without importing those modules at class definition time. The annotations are stored as strings and evaluated lazily.

**Before (would fail without pyodbc installed):**

```python
class MSSQLConnection:
    def __init__(self, config: ConnectionConfig):
        self._connection: Optional[pyodbc.Connection] = None  # requires pyodbc at import time
```

**After (works without pyodbc installed):**

```python
from __future__ import annotations  # all annotations become strings

class MSSQLConnection:
    def __init__(self, config: ConnectionConfig):
        self._connection: Optional[pyodbc.Connection] = None  # str eval, no import needed
```

### 3. Optional Dependency Groups

Python packaging technique where heavy dependencies are declared as `[project.optional-dependencies] agent = [...]` in `pyproject.toml`. This enables:

- **CLI image**: `pip install -e .` — installs only core deps (click, rich, requests, pydantic)
- **Agent image**: `pip install -e .[agent]` — installs core + agent deps (jpype, fastapi, uvicorn, pyodbc, etc.)
- **5x image size reduction** (900MB → 180MB) for the common per-command path

### 4. Container Health Check Protocol

A lightweight health-check protocol enables the shell wrapper to detect running agents:

- Agent exposes `GET /health` endpoint returning `{"status": "healthy", ...}`
- Detection uses `curl -s --max-time 2 http://127.0.0.1:8765/health`
- Auto-start loop polls health endpoint up to 15 times (1s apart)
- CLI's `AS400AgentClient` also checks health before routing requests

### 5. Agent Auto-Start Logic

The shell wrapper (`qadmcli.sh`) implements transparent agent lifecycle:

```bash
# Automatic detection
detect_agent() {
    [ -n "$QADMCLI_AGENT_URL" ] && echo "$QADMCLI_AGENT_URL" && return 0
    podman ps --format '{{.Names}}' | grep -q "^qadmcli-agent$" && ...
    curl -s --max-time 2 http://127.0.0.1:8765/health > /dev/null && ...
    return 1
}

# Automatic start if not found
default_start_agent() {
    ensure_image qadmcli-agent Containerfile.agent
    podman rm -f qadmcli-agent 2>/dev/null || true
    podman run -d --name qadmcli-agent --network=host \
        -e AS400_HOST=... "$AGENT_IMAGE" agent start --foreground
    for i in $(seq 1 15); do
        curl -s --max-time 1 http://127.0.0.1:8765/health && return 0
        sleep 1
    done
}
```

---

## Communication Flow

```
┌─────────────────────────────────────────────────────────────┐
│ CLI Container (per command)    Agent Container (persistent) │
│                                                             │
│ ┌──────────────────────┐       ┌──────────────────────────┐ │
│ │ mockup.py            │       │ FastAPI server.py        │ │
│ │  → agent_client.py   │ HTTP  │  → /health              │ │
│ │    POST /sql/batch   │──────►│  → /sql/batch           │ │
│ │    {sql, params, lib}│       │  → /mockup/generate     │ │
│ │                      │◄──────│                          │ │
│ │  ← {status, rows,   │  JSON  │  ConnectionPool          │ │
│ │     execution_time}  │       │   → JVMManager (jpype)   │ │
│ │                      │       │   → JT400 JDBC           │ │
│ │                      │       │   → AS400 Server         │ │
│ └──────────────────────┘       └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Request/Response example (batch insert):**

```json
// Request: POST /sql/batch
{
  "sql": "INSERT INTO GSLIBTST.THAI_TEST (ID, NAME) VALUES (?, ?)",
  "params": [
    {"1": 1, "2": "สมชาย สุขใจ"},
    {"1": 2, "2": "วิชัย ทองดี"}
  ],
  "library": "GSLIBTST"
}

// Response: 200 OK
{
  "status": "success",
  "rows_affected": 2,
  "execution_time_ms": 45.2
}
```

---

## Performance

| Metric | Before (Monolithic) | After (Split + Agent) | Improvement |
|---|---|---|---|
| Per-command container startup | 4-6s | < 1s | ~6x |
| JVM startup per command | 2-3s | 0s (once, amortized) | ∞ |
| AS400 connection per command | 1-2s | 0s (pooled) | ∞ |
| 500-row mockup inserts | ~50s | ~2.5s | 20x |
| 1000-row mockup generation | ~100s | ~5s | 20x |
| Steady-state throughput | ~10 rows/sec | ~200 rows/sec | 20x |
| CLI image size | ~900 MB | ~180 MB | 5x smaller |

### Startup Cost Breakdown

**First command (cold start):**
```
Build CLI image:      ~20s  (once, cached thereafter)
Build agent image:    ~60s  (once, cached thereafter)
Agent JVM startup:    2-3s  (once per agent start)
Agent pool init:      1-2s  (once per agent start)
Total first run:      ~85s  (one-time cost)
```

**Subsequent commands (steady state):**
```
CLI container start:  <1s
Agent already running: 0s
Connection from pool: <0.01s
SQL execution:        as needed
Container cleanup:    <1s
Total per command:    ~1-2s
```

---

## Configuration

### Environment Variables

All variables are auto-loaded from `.env` by `qadmcli.sh`:

| Variable | Purpose | Default |
|---|---|---|
| `AS400_HOST` | AS400 server address | — |
| `AS400_USER` | AS400 username | — |
| `AS400_PASSWORD` | AS400 password | — |
| `AS400_LIBRARY` | Default library | `*LIBL` |
| `QADMCLI_AGENT_URL` | Agent URL (auto-detected) | — |
| `MSSQL_HOST` / `USER` / `PASSWORD` | MSSQL connection | — |
| `JT400_JAR` | Custom jt400.jar path | auto-detect |
| `QADMCLI_DEBUG` | Enable debug logging | — |

### Container Images

```bash
# Build CLI image (pure Python, ~180MB)
podman build -t qadmcli-cli -f Containerfile.cli .

# Build agent image (JVM + ODBC + JT400, ~692MB)
podman build -t qadmcli-agent -f Containerfile.agent .
```

### .env File Example

```ini
AS400_HOST=161.82.146.249
AS400_USER=your_username
AS400_PASSWORD=your_password
AS400_LIBRARY=GSLIBTST
```

---

## Usage

### Default: Auto-Start (Recommended)

```bash
cd /home/ubuntu/_qoder/qadmcli

# Just run any command — agent auto-starts on first use
./qadmcli.sh connection check
./qadmcli.sh table list -l GSLIBTST
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000
# First run: ~85s (builds both images + starts agent)
# Subsequent runs: < 2s
```

### Manual Agent Management

```bash
# Stop agent daemon
podman stop qadmcli-agent

# Remove agent container
podman rm qadmcli-agent

# View agent logs
podman logs qadmcli-agent
```

### Override Agent URL

```bash
# Point to remote or host-based agent
export QADMCLI_AGENT_URL=http://192.168.1.100:8765
./qadmcli.sh connection check
```

### Direct Host Usage (Development)

```bash
# Install everything locally
cd /home/ubuntu/_qoder/qadmcli
pip install -e .[agent]

# Run CLI directly (no containers)
qadmcli table list -l GSLIBTST

# Start agent directly
qadmcli agent start --foreground
```

---

## Benefits

- **5x smaller CLI image** (180MB vs 900MB monolithic)
- **20x faster bulk operations** (200 vs 10 rows/sec)
- **Zero per-command JVM overhead** — JVM starts once, stays running
- **Zero per-command connection overhead** — connection pool reuses connections
- **No host dependencies** — everything runs in containers
- **Auto-recovery** — agent restarts if it crashes; qadmcli.sh auto-starts it
- **Backward compatible** — same CLI commands, zero code changes needed

## Trade-offs

- Agent consumes ~692MB disk space and ~512MB RAM persistently
- First command on a cold start takes ~85s (building images + starting agent)
- Port 8765 must be available on the host for agent communication
- Requires Podman for container management
- An additional moving part to monitor (agent daemon)
