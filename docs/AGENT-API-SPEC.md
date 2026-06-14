# QADMCLI Agent API Specification

## Overview

**Protocol:** HTTP/REST  
**Port:** 8765 (default)  
**Content-Type:** `application/json`  
**Base URL:** `http://127.0.0.1:8765`

---

## Architecture

```
┌──────────────────────────────────────┐
│  CLI Container                       │
│  (Python + requests library)         │
│                                      │
│  HTTP POST/GET requests              │
│  Content-Type: application/json      │
│                                      │
│  Example:                            │
│  POST /sql/batch                     │
│  {                                   │
│    "sql": "INSERT INTO ...",         │
│    "params": [...]                   │
│  }                                   │
└──────────────┬───────────────────────┘
               │ HTTP/REST API
               │ Port 8765
               │
┌──────────────▼───────────────────────┐
│  Agent Container / Host              │
│  (FastAPI + Uvicorn)                 │
│                                      │
│  Endpoints:                          │
│  - GET  /health                      │
│  - GET  /status                      │
│  - POST /sql/execute                 │
│  - POST /sql/batch                   │
│  - POST /mockup/insert               │
│  - POST /mockup/update               │
│  - POST /mockup/delete               │
│                                      │
│  Internal:                           │
│  - JVM (JPype)                       │
│  - JT400 Connection Pool             │
│  - Bulk execution                    │
└──────────────┬───────────────────────┘
               │ JT400 Protocol
               ▼
        ┌──────────────┐
        │ AS400 Server │
        └──────────────┘
```

---

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /health`

**Purpose:** Check if agent is alive and healthy

**Request:**
```http
GET /health HTTP/1.1
Host: 127.0.0.1:8765
```

**Response (200 OK):**
```json
{
  "status": "healthy",
  "jvm_running": true,
  "jt400_version": "JT400 loaded (JVM running)",
  "pool_stats": {
    "total_connections": 5,
    "active_connections": 0,
    "idle_connections": 5,
    "total_queries": 1234,
    "avg_query_time_ms": 45.32
  },
  "uptime_seconds": 7200.5,
  "timestamp": "2024-05-19T14:30:00.000000"
}
```

**Response (503 Unhealthy):**
```json
{
  "status": "unhealthy",
  "jvm_running": false,
  "jt400_version": "JVM not started",
  "pool_stats": null,
  "uptime_seconds": 0,
  "timestamp": "2024-05-19T14:30:00.000000"
}
```

**CLI Usage:**
```bash
curl http://127.0.0.1:8765/health | jq
```

---

### 2. Agent Status

**Endpoint:** `GET /status`

**Purpose:** Get detailed agent status and pool statistics

**Request:**
```http
GET /status HTTP/1.1
Host: 127.0.0.1:8765
```

**Response (200 OK):**
```json
{
  "agent_version": "0.1.0",
  "jvm_status": "running",
  "jt400_status": "loaded",
  "connection_pool": {
    "size": 5,
    "active": 2,
    "idle": 3,
    "total_queries": 1234,
    "total_errors": 5,
    "avg_query_time_ms": 45.32,
    "uptime": "2h 0m"
  },
  "uptime": "2h 0m"
}
```

**CLI Usage:**
```bash
curl http://127.0.0.1:8765/status | jq
```

---

### 3. Execute Single SQL

**Endpoint:** `POST /sql/execute`

**Purpose:** Execute a single SQL statement

**Request:**
```http
POST /sql/execute HTTP/1.1
Host: 127.0.0.1:8765
Content-Type: application/json

{
  "sql": "SELECT COUNT(*) FROM GSLIBTST.THAI_TEST",
  "library": "GSLIBTST"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "rows_affected": 1,
  "execution_time_ms": 25.43
}
```

**Response (500 Error):**
```json
{
  "detail": "SQL0204: Table THAI_TEST not found"
}
```

**CLI Usage:**
```bash
curl -X POST http://127.0.0.1:8765/sql/execute \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT COUNT(*) FROM GSLIBTST.THAI_TEST",
    "library": "GSLIBTST"
  }' | jq
```

---

### 4. Execute Batch SQL (FAST!)

**Endpoint:** `POST /sql/batch`

**Purpose:** Execute batch SQL with parameters (bulk insert/update/delete)

**Request:**
```http
POST /sql/batch HTTP/1.1
Host: 127.0.0.1:8765
Content-Type: application/json

{
  "sql": "INSERT INTO GSLIBTST.THAI_TEST (ID, FIRSTNAME_TH, LASTNAME_TH, STORE_ID, FULLNAME_TH, CREATED_AT) VALUES (?, ?, ?, ?, ?, ?)",
  "params": [
    {
      "1": 1001,
      "2": "สมชาย",
      "3": "สุขใจ",
      "4": "STORE01",
      "5": "สมชาย สุขใจ",
      "6": "2024-05-19 14:30:00"
    },
    {
      "1": 1002,
      "2": "วิชัย",
      "3": "ทองดี",
      "4": "STORE02",
      "5": "วิชัย ทองดี",
      "6": "2024-05-19 14:30:01"
    },
    {
      "1": 1003,
      "2": "ประเสริฐ",
      "3": "มั่นคง",
      "4": "STORE01",
      "5": "ประเสริฐ มั่นคง",
      "6": "2024-05-19 14:30:02"
    }
  ],
  "library": "GSLIBTST"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "rows_affected": 3,
  "execution_time_ms": 125.67
}
```

**CLI Usage:**
```bash
curl -X POST http://127.0.0.1:8765/sql/batch \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "INSERT INTO GSLIBTST.THAI_TEST (ID, FIRSTNAME_TH, LASTNAME_TH) VALUES (?, ?, ?)",
    "params": [
      {"1": 1, "2": "สมชาย", "3": "สุขใจ"},
      {"1": 2, "2": "วิชัย", "3": "ทองดี"}
    ],
    "library": "GSLIBTST"
  }' | jq
```

---

### 5. Mockup Bulk Insert

**Endpoint:** `POST /mockup/insert`

**Purpose:** Execute bulk insert for mock data generation

**Request:** (Same as `/sql/batch`)
```http
POST /mockup/insert HTTP/1.1
Host: 127.0.0.1:8765
Content-Type: application/json

{
  "sql": "INSERT INTO GSLIBTST.THAI_TEST (...) VALUES (...)",
  "params": [...500 rows...],
  "library": "GSLIBTST"
}
```

**Response:** (Same as `/sql/batch`)
```json
{
  "status": "success",
  "rows_affected": 500,
  "execution_time_ms": 2100.50
}
```

---

### 6. Mockup Bulk Update

**Endpoint:** `POST /mockup/update`

**Purpose:** Execute bulk update for mock data

**Request:**
```http
POST /mockup/update HTTP/1.1
Host: 127.0.0.1:8765
Content-Type: application/json

{
  "sql": "UPDATE GSLIBTST.THAI_TEST SET FIRSTNAME_TH = ?, LASTNAME_TH = ? WHERE ID = ?",
  "params": [
    {"1": "ชื่อใหม่", "2": "นามสกุลใหม่", "3": 1001},
    {"1": "ชื่อใหม่2", "2": "นามสกุลใหม่2", "3": 1002}
  ],
  "library": "GSLIBTST"
}
```

**Response:**
```json
{
  "status": "success",
  "rows_affected": 300,
  "execution_time_ms": 1200.30
}
```

---

### 7. Mockup Bulk Delete

**Endpoint:** `POST /mockup/delete`

**Purpose:** Execute bulk delete for mock data

**Request:**
```http
POST /mockup/delete HTTP/1.1
Host: 127.0.0.1:8765
Content-Type: application/json

{
  "sql": "DELETE FROM GSLIBTST.THAI_TEST WHERE ID = ?",
  "params": [
    {"1": 1001},
    {"1": 1002},
    {"1": 1003}
  ],
  "library": "GSLIBTST"
}
```

**Response:**
```json
{
  "status": "success",
  "rows_affected": 200,
  "execution_time_ms": 800.25
}
```

---

## How CLI Uses the API

### Python Code (Inside CLI Container):

```python
import requests
import os

class AS400AgentClient:
    def __init__(self, agent_url=None):
        # Auto-detect agent URL from environment
        self.agent_url = agent_url or os.getenv('QADMCLI_AGENT_URL', 'http://127.0.0.1:8765')
    
    def health_check(self):
        """Check if agent is healthy"""
        response = requests.get(f"{self.agent_url}/health", timeout=2)
        return response.json()
    
    def execute_batch(self, sql: str, params: list, library: str = ""):
        """Execute batch SQL via agent"""
        payload = {
            "sql": sql,
            "params": params,
            "library": library
        }
        
        response = requests.post(
            f"{self.agent_url}/sql/batch",
            json=payload,
            timeout=300  # 5 minutes for large batches
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Agent error: {response.text}")
    
    def mockup_insert(self, sql: str, rows: list, library: str):
        """Bulk insert for mockup generation"""
        # Convert rows to params format
        params = []
        for row in rows:
            param_dict = {str(i+1): val for i, val in enumerate(row)}
            params.append(param_dict)
        
        return self.execute_batch(sql, params, library)
    
    def mockup_update(self, sql: str, updates: list, library: str):
        """Bulk update for mockup generation"""
        return self.execute_batch(sql, updates, library)
    
    def mockup_delete(self, sql: str, ids: list, library: str):
        """Bulk delete for mockup generation"""
        params = [{"1": pk} for pk in ids]
        return self.execute_batch(sql, params, library)


# Example usage in mockup.py
agent = AS400AgentClient()

# Check agent is available
if agent.health_check()['status'] == 'healthy':
    # Use agent for bulk operations
    result = agent.mockup_insert(
        sql="INSERT INTO GSLIBTST.THAI_TEST (...) VALUES (...)",
        rows=[
            (1001, "สมชาย", "สุขใจ", ...),
            (1002, "วิชัย", "ทองดี", ...),
            # ... 500 rows
        ],
        library="GSLIBTST"
    )
    print(f"Inserted {result['rows_affected']} rows in {result['execution_time_ms']}ms")
else:
    # Fallback to direct JT400
    print("Agent not available, using direct connection")
```

---

## Network Configuration

### Option 2: Agent on Host

```bash
# Agent listens on localhost:8765
qadmcli agent start --host 127.0.0.1 --port 8765

# Container uses --network=host to access localhost
sudo podman run --network=host ...
```

**Network flow:**
```
Container (localhost:8765) → Host loopback (127.0.0.1:8765) → Agent
```

### Option 3: Agent in Container

```bash
# Agent container uses --network=host
sudo podman run -d --name qadmcli-agent --network=host ...

# CLI container also uses --network=host
sudo podman run --network=host ...
```

**Network flow:**
```
CLI Container (localhost:8765) → Host network namespace → Agent Container (localhost:8765)
```

---

## Error Handling

### HTTP Status Codes:

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Parse response JSON |
| 400 | Bad Request | Check request format |
| 500 | Internal Error | Agent execution failed |
| 503 | Service Unavailable | Agent not ready / No connections |

### Error Response Format:

```json
{
  "detail": "Error message here"
}
```

### CLI Error Handling:

```python
try:
    result = agent.execute_batch(sql, params, library)
    print(f"Success: {result['rows_affected']} rows")
except requests.exceptions.ConnectionError:
    print("Agent not available, falling back to direct JT400")
    use_direct_connection()
except requests.exceptions.Timeout:
    print("Agent request timed out")
    raise
except Exception as e:
    print(f"Agent error: {e}")
    raise
```

---

## Performance Characteristics

### Single SQL Execution:

```
CLI → HTTP POST /sql/execute → Agent → JT400 → AS400
Latency: ~25-50ms per statement
```

### Batch SQL Execution (FAST):

```
CLI → HTTP POST /sql/batch (500 rows) → Agent → JT400 Batch API → AS400
Latency: ~2000ms for 500 rows = 4ms per row (10x faster!)
```

### Why Batch is Faster:

1. **Single HTTP request** instead of 500 requests
2. **JT400 PreparedStatement.addBatch()** instead of individual execute()
3. **Single commit** instead of 500 commits
4. **Connection reuse** from pool (no connect/disconnect overhead)

---

## Complete Example: Mockup Generation Flow

```python
# CLI Container (mockup.py)
def generate_mock_data_via_agent(config):
    agent = AS400AgentClient()
    
    # 1. Check agent health
    health = agent.health_check()
    if health['status'] != 'healthy':
        raise Exception("Agent unhealthy")
    
    # 2. Generate INSERT batch
    insert_sql = "INSERT INTO GSLIBTST.THAI_TEST (ID, FIRSTNAME_TH, ...) VALUES (?, ?, ...)"
    insert_rows = generate_insert_data(500)  # Generate 500 rows
    
    result = agent.mockup_insert(insert_sql, insert_rows, "GSLIBTST")
    print(f"Inserted: {result['rows_affected']} rows in {result['execution_time_ms']:.2f}ms")
    
    # 3. Generate UPDATE batch
    update_sql = "UPDATE GSLIBTST.THAI_TEST SET FIRSTNAME_TH = ? WHERE ID = ?"
    update_rows = generate_update_data(300)
    
    result = agent.mockup_update(update_sql, update_rows, "GSLIBTST")
    print(f"Updated: {result['rows_affected']} rows in {result['execution_time_ms']:.2f}ms")
    
    # 4. Generate DELETE batch
    delete_sql = "DELETE FROM GSLIBTST.THAI_TEST WHERE ID = ?"
    delete_ids = generate_delete_ids(200)
    
    result = agent.mockup_delete(delete_sql, delete_ids, "GSLIBTST")
    print(f"Deleted: {result['rows_affected']} rows in {result['execution_time_ms']:.2f}ms")
```

---

## API Testing

### Using curl:

```bash
# Health check
curl http://127.0.0.1:8765/health | jq

# Status
curl http://127.0.0.1:8765/status | jq

# Single SQL
curl -X POST http://127.0.0.1:8765/sql/execute \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1 FROM SYSIBM.SYSDUMMY1"}'

# Batch SQL
curl -X POST http://127.0.0.1:8765/sql/batch \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "INSERT INTO GSLIBTST.TEST (ID, NAME) VALUES (?, ?)",
    "params": [
      {"1": 1, "2": "Test1"},
      {"1": 2, "2": "Test2"}
    ]
  }'
```

### Using Python requests:

```python
import requests

# Health check
response = requests.get("http://127.0.0.1:8765/health")
print(response.json())

# Batch insert
response = requests.post(
    "http://127.0.0.1:8765/sql/batch",
    json={
        "sql": "INSERT INTO ...",
        "params": [...],
        "library": "GSLIBTST"
    }
)
print(response.json())
```

---

## Security Considerations

### Current Implementation:
- ⚠️ **No authentication** (assumes localhost access only)
- ⚠️ **No encryption** (HTTP, not HTTPS)
- ✅ Binds to `127.0.0.1` only (not exposed to network)

### Production Recommendations:
- Add API key authentication
- Use HTTPS with TLS certificates
- Implement rate limiting
- Add request validation
- Enable CORS only for trusted origins

---

## Summary

| Aspect | Detail |
|--------|--------|
| **Protocol** | HTTP/REST |
| **Port** | 8765 |
| **Content-Type** | `application/json` |
| **Framework** | FastAPI + Uvicorn |
| **Batch API** | `/sql/batch` (primary for performance) |
| **Mockup APIs** | `/mockup/insert`, `/mockup/update`, `/mockup/delete` |
| **Health Check** | `GET /health` |
| **CLI Library** | Python `requests` |
| **Timeout** | 300s for batch operations |
| **Error Format** | `{"detail": "error message"}` |

---

## Journal Command → Agent API Mapping

All 13 journal CLI commands delegate to the agent when `QADMCLI_AGENT_URL` is set. Each command uses one or both of these client methods:

| Client Method | Agent Endpoint | Purpose |
|---|---|---|
| `client.query()` | `POST /sql/query` | SELECT queries (read data) |
| `client.execute()` | `POST /sql/execute` | DDL/DML / CL commands via `CALL QSYS2.QCMDEXC` |

---

### Read-Only Commands (use `client.query()` → `POST /sql/query`)

| CLI Command | SQL / System Table | Purpose |
|---|---|---|
| `journal status [-j JRN] [-l LIB]` | `SELECT * FROM QSYS2.JOURNAL_INFO` | Journal configuration & status |
| `journal info -t TABLE -l LIB` | `SELECT * FROM QSYS2.JOURNAL_INFO` | Journal info for specific table(s) |
| `journal entries -t TABLE -l LIB [--range R]` | `SELECT * FROM QSYS2.JOURNAL_ENTRY_INFO` | Journal entry contents with filtering |
| `journal table-entries -j JRN -l LIB [--range R]` | `SELECT * FROM QSYS2.JOURNAL_ENTRY_INFO` | Table-level journal entries |
| `journal receivers -j JRN -l LIB` | `SELECT * FROM QSYS2.JOURNAL_RECEIVER_INFO` | Receiver chain display |
| `journal receiver-info -j JRN -l LIB` | `SELECT * FROM QSYS2.JOURNAL_RECEIVER_INFO` | Detailed receiver information |
| `journal health [-j JRN] [-l LIB]` | `SELECT * FROM QSYS2.JOURNAL_INFO` | Health check (threshold warnings) |

**Agent implementation pattern:**
```python
client = AS400AgentClient(agent_url)
result = client.query("SELECT ... FROM QSYS2.JOURNAL_INFO WHERE ...", params=[...])
for row in result["rows"]:
    # process row data
```

---

### Write Commands (use `client.execute()` → `POST /sql/execute`)

All write commands execute CL commands via `CALL QSYS2.QCMDEXC(?, ?)`.

| CLI Command | CL Command | Action |
|---|---|---|
| `journal disable -t TABLE -l LIB` | `ENDJRNPF FILE(lib/table) JRN(*FILE)` | End journaling on a table |
| `journal enable -t TABLE -l LIB -j JRN -l jlib [--images *BOTH]` | `STRJRNPF FILE(lib/table) JRN(jlib/jrn) IMAGES(*BOTH) OMTJRNE(*OPNCLO)` | Start journaling on a table |
| `journal create-receiver -n NAME -l LIB [--threshold N]` | `CRTJRNRCV JRNRCV(lib/name) THRESHOLD(N)` | Create a new journal receiver |
| `journal create -n NAME -l LIB -r RECV -rlib RLIB [--reuse *NO]` | `CRTJRN JRN(lib/name) JRNRCV(rlib/recv) ...` | Create a new journal |
| `journal rollover -j JRN -l LIB [--rcv NAME]` | `CHGJRN JRN(lib/jrn) JRNRCV(*GEN)` | Roll journal to new receiver |
| `journal cleanup -j JRN -l LIB [--keep N] [--force]` | `DLTJRNRCV JRNRCV(lib/name)` | Delete old detached receivers |

**Agent implementation pattern (DDL/DML via QCMDEXC):**
```python
client = AS400AgentClient(agent_url)
cmd = f"ENDJRNPF FILE({lib}/{table}) JRN(*FILE)"
client.execute("CALL QSYS2.QCMDEXC(?, ?)", params=[cmd, len(cmd.encode('utf-8'))])
```

---

### Hybrid Commands (query + execute in sequence)

Some write commands first query the agent for metadata, then execute CL commands:

| CLI Command | Phase 1: Query | Phase 2: Execute |
|---|---|---|
| `journal disable` (wildcard) | `QSYS2.SYSTABLES` — list matching tables | `ENDJRNPF` for each matched table |
| `journal enable` (wildcard) | `QSYS2.SYSTABLES` — list matching tables | `STRJRNPF` for each matched table |
| `journal rollover` | `QSYS2.JOURNAL_RECEIVER_INFO` — get current attached receiver | `CHGJRN` then re-query new receiver name |
| `journal cleanup` | `QSYS2.JOURNAL_RECEIVER_INFO` — build cleanup plan (detached receivers) | `DLTJRNRCV` for each receiver to delete |

---

### Agent API Endpoint Summary

| Endpoint | Method | CLI Method | Used By |
|---|---|---|---|
| `/sql/query` | POST | `client.query()` | All 7 journal readonly commands |
| `/sql/execute` | POST | `client.execute()` | All 6 journal write commands |
| `/sql/batch` | POST | `client.execute_batch()` | Mockup generation (insert/update/delete) |
| `/mockup/insert` | POST | `client.mockup_insert()` | Mockup generation |
| `/mockup/update` | POST | `client.mockup_update()` | Mockup generation |
| `/mockup/delete` | POST | `client.mockup_delete()` | Mockup generation |
| `/health` | GET | `client._check_health()` | Health check / auto-detection |
| `/status` | GET | — | Agent status details |

