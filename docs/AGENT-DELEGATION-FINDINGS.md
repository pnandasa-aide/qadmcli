# Agent Delegation & Performance Fixes

## 1. CLI Slowness — `podman images` Overhead

**Root Cause:** `ensure_image()` in `qadmcli.sh` calls `podman images --format "{{.Repository}}"` on every invocation. This takes ~12 seconds because podman's containers/storage scans 303 overlay-image + 393 overlay-layer metadata files on each call — even on local ext4 storage.

**Fix:** Added a time-based image existence cache (300s TTL) at `~/.cache/qadmcli/image-check/<image-name>`. When the cache is fresh, the 12s `podman images` call is skipped entirely.

**Result:** Warm invocation: ~2s (down from ~14s) — **7x improvement**.

**Additional:** Fixed TTY handling — `-it` flags now only applied when stdin/stdout are actual terminals, preventing "not a terminal" errors in non-interactive use.

---

## 2. Agent Delegation — `connection test-as400` Fails in Slim CLI

**Problem:** The slim CLI container lacks `jpype` / `jaydebeapi` (intentionally — they're heavy Java dependencies). Running `connection test-as400` in the slim CLI resulted in `ModuleNotFoundError: No module named 'jpype'`.

**Fix:** Wired the CLI to delegate AS400 connection testing to the agent via REST API when `QADMCLI_AGENT_URL` is set.

### Changes:

**Agent side** (`qadmcli_agent/`):
- **`server.py`:** Added `POST /sql/query` endpoint accepting `SQLRequest` and returning `QueryResponse` (columns, rows, row_count, execution_time_ms).
- **`connection_pool.py`:**
  - Added `JDBCResultCursor.get_column_names()` — extracts column labels from JDBC ResultSetMetaData
  - Added `JDBCResultCursor.fetchall_dicts()` — fetches rows as dicts with Java→Python type conversion
  - Added `ConnectionPool.execute_query(sql, params)` — full query lifecycle: borrow connection → execute → convert types → release → return structured dict

**CLI side** (`src/qadmcli/`):
- **`db/agent_client.py`:** Added `query(sql, library, params)` method that calls `POST /sql/query` on the agent
- **`cli_commands/connection_commands.py`:** Modified `connection_test_as400` to:
  1. Check for `QADMCLI_AGENT_URL` env var
  2. If set, try `_test_connection_via_agent()` which queries `QSYS2.QSQPTABL` for version info
  3. Fall back to direct JT400 if agent unavailable

---

## 3. Agent Startup Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| `Config file not found: config/connection.yaml` | Click's `type=click.Path(exists=True)` validates at parse time, before the CLI action runs | Removed `exists=True`; made `get_config_path()` return `Path \| None` when default file is missing |
| `java.awt.HeadlessException` | JT400 tries to initialize AWT in a container without X11/display | Added `-Djava.awt.headless=true` to `jpype.startJVM()` args in `jvm_manager.py` |
| Empty credentials in pool | `agent.json` has empty `user`/`password` fields when started via `qadmcli.sh` (env vars not written to config file) | Added `os.getenv()` fallback in `server.py` startup — credentials from container environment variables are used when `agent.json` has empty values |

---

## 4. Connection Pool Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| `AttributeError: 'AS400JDBCConnectionImpl' object has no attribute 'setLibraryList'` | Newer JT400 driver versions return `AS400JDBCConnectionImpl` from `DriverManager.getConnection()`, which lacks the legacy `setLibraryList()` method | Removed `setLibraryList()` call; library list is already set via JDBC URL path and `libraries` connection property |
| `pydantic_core.ValidationError: Input should be a valid string` | Pydantic v2 strict mode rejects `java.lang.String` objects when field type is `List[str]` | Added `str(name)` conversion in `get_column_names()` to explicitly convert Java String to Python str |

---

## 5. Architecture Summary

```
┌──────────────┐     HTTP (REST API)     ┌──────────────────┐
│  qadmcli.sh  │ ──────────────────────> │  qadmcli-agent   │
│  (slim CLI)  │    POST /sql/query      │  (JVM + JT400)   │
│              │    POST /sql/execute    │  ┌────────────┐  │
│  No jpype    │    POST /sql/batch      │  │Connection  │  │
│  No JT400    │    GET  /health         │  │Pool (5)    │  │
│  ~180MB img  │    GET  /status         │  │JT400→AS400 │  │
└──────────────┘                         │  └────────────┘  │
                                         │  ~692MB image    │
                                         └──────────────────┘
```

The CLI container mounts the project directory and runs with `--network=host` so it can reach the agent at `http://127.0.0.1:8765`. The agent URL is passed via `QADMCLI_AGENT_URL` environment variable.

For commands requiring JT400/ODBC (connection testing, SQL execution, mockup generation), the CLI delegates to the agent. For all other commands (configuration, file operations), it operates directly.
