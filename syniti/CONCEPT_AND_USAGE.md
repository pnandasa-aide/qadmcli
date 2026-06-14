# Syniti Metadata Customization & Update Concepts

This document explains the concepts, mechanics, and usage of the script used to customize Syniti replication metadata when simulating/migrating from a source AS400 library (like `SYNITI`) to another library (like `TBLIBTST`).

---

## 1. Concepts & Replication Mechanics

### 1.1 The Role of Groups (`DBMMGroups`)
* **What are Groups?** Replications in Syniti can be organized into one or more groups (e.g. `RRN`, `Normal`).
* **Do they hold replication status?** **No**. The Group entities (`DBMMGroups`) contain only scheduling, mirroring intervals, conflict resolution rules, buffers, and priorities. They do **not** contain sequence numbers, transaction timestamps, or journal coordinates.
* **Should we update the Group?** **No**. There is no transaction sequence or library-specific status information within `DBMMGroups`. Hence, they do not need to be updated.

### 1.2 What Needs to Be Updated?
To shift replications from the simulated `SYNITI` library/journal receiver to `TBLIBTST` and point them to the correct point-in-time sequence, we need to modify three parts of the metadata XML:
1. **`DBMMSchemas`**: Change the `<Name>` tag from the old library name (`SYNITI`) to the new library name (`TBLIBTST`).
2. **`DBMMReplStatuses`**:
   * Change properties: Update `ReceiverLibrary`, `JournalLibrary`, `JournalName`, and `ReceiverName`.
   * Update transaction logs: Set `TransactionID` (Sequence number) and `TransactionTS` (.NET Ticks timestamp) to coordinate the replication start point.
3. **`DBMMReplications`**: Update properties like `JournalLibrary`, `JournalName`, and `ReceiverLibrary` to match the new library and system journals (e.g., `QSQJRN`).

### 1.3 Querying Journal Configuration and Current Coordinates

You can determine the active journal name, receiver, images mode (`*BOTH`), and the target sequence number/timestamp coordinates using either the `qadmcli` tool or direct SQL queries.

#### Method A: Using `qadmcli` CLI commands

1.  **Check Journaling Status & Images Mode:**
    Run the `journal check` command to inspect if a table is journaled, see the attached receiver library/name, and verify if it uses `*BOTH` images:
    ```bash
    python3 -m qadmcli.cli journal check --library TBLIBTST --table CHDRPF50
    ```
    *Output snippet:*
    ```text
    Table: TBLIBTST.CHDRPF50
    Journaled: Yes
    Journal: TBLIBTST.QSQJRN
    Receiver: TBLIBTST.QSQJRN0001
    Images: *BOTH
    ```

2.  **Retrieve Current Transaction Sequence & Timestamp:**
    Use the `journal last-txn` command to query the attached journal receiver and retrieve the latest sequence number and converted .NET ticks:
    ```bash
    python3 -m qadmcli.cli journal last-txn -t TBLIBTST.CHDRPF50
    ```
    This fetches the `LAST_SEQUENCE_NUMBER` and automatically converts the attach timestamp to .NET Ticks (needed for Syniti).

#### Method B: Using SQL Queries

If running queries directly on the AS400 database:

1.  **Verify Journal name, Receiver, and images mode (`*BOTH`):**
    ```sql
    SELECT JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES
    FROM QSYS2.JOURNALED_OBJECTS
    WHERE OBJECT_NAME = 'CHDRPF50' 
      AND OBJECT_LIBRARY = 'TBLIBTST' 
      AND OBJECT_TYPE = '*FILE';
    ```
    *If `JOURNAL_IMAGES` returns `*BOTH`, journaling is correctly capturing both before and after images (required for bi-directional synchronization).*

2.  **Retrieve Current Receiver & Last Sequence Number:**
    ```sql
    SELECT LAST_SEQUENCE_NUMBER, ATTACH_TIMESTAMP, JOURNAL_RECEIVER_NAME, JOURNAL_RECEIVER_LIBRARY, STATUS
    FROM QSYS2.JOURNAL_RECEIVER_INFO
    WHERE JOURNAL_LIBRARY = 'TBLIBTST' 
      AND JOURNAL_NAME = 'QSQJRN' 
      AND STATUS = 'ATTACHED';
    ```

---

## 2. Script Usage: `update_metadata.py`

The helper script `update_metadata.py` processes the Syniti metadata XML. It dynamically parses parameter inputs, handles datetime-to-ticks conversion, and performs targeted replacements.

### Parameters
```bash
python3 update_metadata.py --help
```

* `-m`, `--xml`: Path to the Syniti metadata XML file (default: `/home/ubuntu/_qoder/qadmcli/syniti/Metadata_deves_1.xml`).
* `-s`, `--seq`: Target replication TransactionID / Sequence Number (e.g. `100627`).
* `-t`, `--ts`: Target replication TransactionTS / Timestamp (supports `YYYY-MM-DD HH:MM:SS.ffffff` format or raw `.NET ticks`).
* `--src-lib`: Source library/schema to replace (default: `SYNITI`).
* `--trg-lib`: Target library/schema to replace with (default: `TBLIBTST`).
* `--src-jrn`: Source journal name to replace (default: `DSJRN`).
* `--trg-jrn`: Target journal name to replace with (default: `QSQJRN`).
* `--src-rcv`: Source receiver name to replace (default: `DSJRNRCV`).
* `--trg-rcv`: Target receiver name to replace with (default: `QSQJRN`).

---

## 3. Practical Examples

### Example A: Update sequence and timestamp only (keeping default library maps)
To configure replication coordinates for sequence `100627` at datetime `2026-06-03 08:03:15.326656`:
```bash
python3 update_metadata.py \
  --seq 100627 \
  --ts "2026-06-03 08:03:15.326656"
```

### Example B: Custom Source/Target Libraries & Journals
If migrating from library `TESTLIB` to `PRODLIB`, mapping journal `MYJRN` to `PRODJRN`:
```bash
python3 update_metadata.py \
  --xml Metadata_deves_1.xml \
  --seq 100627 \
  --ts "2026-06-03 08:03:15.326656" \
  --src-lib TESTLIB \
  --trg-lib PRODLIB \
  --src-jrn MYJRN \
  --trg-jrn PRODJRN \
  --src-rcv MYJRNRCV \
  --trg-rcv PRODJRN
```

*Note: The script automatically creates a backup of the original XML file as `<filename>.bak_script` before making changes.*

---

## 4. Metadata Field Value Reference

The following are the standard definitions and integer mappings used in Syniti Data Replication (formerly DBMoto) for replications within the `DBMMReplications` element:

### 4.1 `ReplMode` (Replication Mode)
Defines the replication mechanism configured for the table.
*   **`1` (Refresh):** Snapshot mode. Performs a full copy of the source table to the target.
*   **`2` (Mirroring):** One-way real-time Change Data Capture (CDC). Captures inserts/updates/deletes from source transaction logs and applies them to target.
*   **`4` (Synchronization):** Bi-directional replication. Synchronizes changes both ways and handles conflicts according to defined priorities.

### 4.2 `ReplStatus` (Replication Status)
Represents the current execution state of the replication task.
*   **`0` (Stopped):** The replication task is stopped or inactive.
*   **`1` (Running):** The replication is actively executing.
*   **`2` (Error):** The replication has suspended or encountered a fatal error.

### 4.3 `ReplInitStatus` (Initialization Status)
Represents the state of replication initialization (performing the initial load).
*   **`0` (Uninitialized):** Replication has not been initialized yet.
*   **`1` (Initializing):** The initial load / refresh is currently in progress.
*   **`2` (Initialized):** The initial load is complete and replication is ready for real-time mirroring.

### 4.4 `ReplLastExit` & `ReplHistoryExit` (Execution Exit Status)
These fields track execution outcomes mapping to the API's `ReplExit` enumeration:
*   **`0` (Success):** Executed successfully without issues.
*   **`1` (Warning):** Completed with non-fatal warnings.
*   **`2` (Errors):** Finished with execution errors.
*   **`3` (Aborted):** Execution was aborted.
*   **`4` (Stopped):** Task was stopped.
*   **`5` (Cleared):** The history status was manually cleared by an administrator.

*Note: `ReplLastExit` represents only the very last run, while `ReplHistoryExit` maintains the failure state persistently since the last manual clear.*

