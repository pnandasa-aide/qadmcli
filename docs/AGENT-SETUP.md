# QADMCLI Setup Guide

## Quick Start (Container-Based, Default)

**No pip install required. Everything runs in containers.**

### 1. Prerequisites

- Podman installed (`sudo apt install podman`)
- Podman machine running (macOS/Windows only)
- `.env` file with AS400 credentials (see Step 3)

### 2. Setup (One-Time)

```bash
cd /home/ubuntu/_qoder/qadmcli

# Copy and edit environment file
cp .env.example .env
# Edit .env with your AS400 credentials

# That's it! Everything else is automatic.
```

### 3. Environment Variables

Create or edit `.env` in the `qadmcli/` directory:

```ini
AS400_HOST=161.82.146.249
AS400_USER=your_username
AS400_PASSWORD=your_password
AS400_LIBRARY=GSLIBTST
```

The `qadmcli.sh` script auto-loads `.env` from the current directory or parent directory.

### 4. Run Commands

```bash
# First run: builds CLI + agent images, starts agent (~85s one-time cost)
# Subsequent runs: < 2s
./qadmcli.sh connection check
./qadmcli.sh table list -l GSLIBTST
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000

# Stop agent when done
podman stop qadmcli-agent

# Remove agent container (will be recreated on next run)
podman rm qadmcli-agent
```

**What happens on first run:**

1. `qadmcli-cli` image is built (~20s, cached thereafter)
2. Agent is detected → none found → `qadmcli-agent` image is built (~60s, cached)
3. Agent container starts → JVM loads → connection pool initializes
4. Slim CLI container runs → command executes → CLI exits
5. Agent persists for next command

---

## Host-Based Setup (Advanced)

Use this when you want to run the agent directly on the host (not containerized), or when doing development.

### 1. Install Everything Locally

```bash
cd /home/ubuntu/_qoder/qadmcli

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install with all dependencies
pip install -e .[agent]
```

### 2. Set Environment Variables

```bash
export AS400_HOST=161.82.146.249
export AS400_USER=your_username
export AS400_PASSWORD=your_password
export AS400_LIBRARY=GSLIBTST
```

### 3. Start the Agent

```bash
# Start agent daemon
qadmcli agent start

# Output:
# 🚀 Starting AS400 Agent...
#    Config: /home/ubuntu/.qadmcli/agent.json
#    Log: /home/ubuntu/.qadmcli/agent.log
#    PID: 12345
#    Waiting for agent to start...
#
# ✅ Agent started successfully!
#    URL: http://127.0.0.1:8765
#    Health: http://127.0.0.1:8765/health

# Check status
qadmcli agent status
# ✅ Agent is running (PID: 12345)
#    JVM: running
#    JT400: loaded
#    Uptime: 0h 2m
```

### 4. Run CLI (picks up host agent automatically)

```bash
# The running agent is detected via curl :8765/health
./qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 1000
# 🔌 Connected to Agent: http://127.0.0.1:8765
```

### 5. Stop the Agent

```bash
qadmcli agent stop
```

---

## Agent Commands

| Command | Description | Context |
|---|---|---|
| `./qadmcli.sh <command>` | Auto-start agent + run CLI | Container |
| `qadmcli agent start` | Start agent daemon on host | Host |
| `qadmcli agent stop` | Stop agent daemon on host | Host |
| `qadmcli agent status` | Check agent status | Host |
| `qadmcli agent logs` | View agent logs | Host |
| `podman stop qadmcli-agent` | Stop containerized agent | Container |
| `podman logs qadmcli-agent` | View container agent logs | Container |

### Start Options (Host Agent)

```bash
qadmcli agent start \
  --host 127.0.0.1 \
  --port 8765 \
  --jt400-path /opt/jt400/jt400.jar \
  --pool-size 5
```

---

## Container Management

### Build Images Manually

```bash
# Build CLI image (~180MB) — pure Python, fast startup
podman build -t qadmcli-cli -f Containerfile.cli .

# Build agent image (~692MB) — JVM + JT400 + ODBC
podman build -t qadmcli-agent -f Containerfile.agent .
```

### Manage Agent Container

```bash
# Check if agent is running
podman ps | grep qadmcli-agent

# View agent logs
podman logs qadmcli-agent

# Stop agent
podman stop qadmcli-agent

# Remove agent container (will auto-recreate on next CLI run)
podman rm qadmcli-agent

# Restart agent (remove + run CLI again to recreate)
podman stop qadmcli-agent
podman rm qadmcli-agent
./qadmcli.sh connection check  # auto-starts fresh agent
```

---

## Configuration

### Agent Config File (Host Agent Only)

When running the agent on the host, config is stored at `~/.qadmcli/agent.json`:

```json
{
  "jt400_path": "/opt/jt400/jt400.jar",
  "pool_size": 5,
  "host": "127.0.0.1",
  "port": 8765,
  "as400": {
    "host": "161.82.146.249",
    "user": "your_user",
    "password": "your_password",
    "library": "GSLIBTST"
  }
}
```

---

## API Endpoints (Agent Direct Access)

When agent is running, you can access these directly:

| Endpoint | Method | Description |
|---|---|---|
| `http://localhost:8765/health` | GET | Health check |
| `http://localhost:8765/status` | GET | Detailed agent status |
| `http://localhost:8765/sql/execute` | POST | Execute single SQL |
| `http://localhost:8765/sql/batch` | POST | Batch SQL execution |

### Example: Direct API Usage

```bash
# Check health
curl http://localhost:8765/health | jq

# Execute SQL
curl -X POST http://localhost:8765/sql/execute \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT COUNT(*) FROM GSLIBTST.THAI_TEST"}'

# Batch insert
curl -X POST http://localhost:8765/sql/batch \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "INSERT INTO GSLIBTST.THAI_TEST (ID, NAME) VALUES (?, ?)",
    "params": [{"1": 1, "2": "สมชาย สุขใจ"}],
    "library": "GSLIBTST"
  }'
```

---

## Performance Comparison

### With Agent (Auto-Start or Manual)
```
100 transactions: ~0.8s (125 rows/sec) — 12x faster
1000 transactions: ~5s (200 rows/sec) — 20x faster
```

### Without Agent (Direct JT400, No Container)
```
100 transactions: ~10s (10 rows/sec)
1000 transactions: ~100s (10 rows/sec)
```

---

## Troubleshooting

### Agent won't start (host agent)

```bash
# Check logs
qadmcli agent logs

# Or tail logs in real-time
tail -f ~/.qadmcli/agent.log
```

### Port already in use

```bash
# Use different port
qadmcli agent start --port 8766

# Or kill process using port 8765
lsof -ti:8765 | xargs kill -9
```

### JT400 not found

```bash
# Specify correct path
qadmcli agent start --jt400-path /path/to/jt400.jar

# Or update config file
nano ~/.qadmcli/agent.json
```

### Container agent not healthy

```bash
# Check logs
podman logs qadmcli-agent

# Restart fresh
podman rm -f qadmcli-agent
./qadmcli.sh connection check  # auto-starts fresh agent
```

---

## Auto-Start Agent on Login (Host Agent)

Add to `~/.bashrc`:

```bash
# Auto-start AS400 agent (host mode only)
if command -v qadmcli &> /dev/null; then
    if ! qadmcli agent status 2>/dev/null | grep -q "running"; then
        echo "Starting AS400 agent..."
        qadmcli agent start &
    fi
fi
```

Or create a systemd service:

```ini
[Unit]
Description=QADMCLI AS400 Agent
After=network.target

[Service]
Type=simple
User=ubuntu
Environment=AS400_HOST=161.82.146.249
Environment=AS400_USER=your_user
Environment=AS400_PASSWORD=your_password
ExecStart=/home/ubuntu/_qoder/qadmcli/venv/bin/qadmcli agent start
ExecStop=/home/ubuntu/_qoder/qadmcli/venv/bin/qadmcli agent stop
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable qadmcli-agent
sudo systemctl start qadmcli-agent
```
