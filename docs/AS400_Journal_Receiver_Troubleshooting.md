# AS400 Journal Receiver Troubleshooting Guide

## Problem Summary

Journal receiver `GSJNRC0002` in library `GSTESTLIB` accumulated **5.7 million entries**, causing severe performance degradation on journal queries. Attempts to delete the receiver after rollover consistently failed with `CPF0006` errors.

## Root Cause

Two compounding issues were found:

1. **Stuck MSGW jobs holding locks:** Previous `DLTJRNRCV` commands were Ctrl+C'd from the client, but the AS400 server jobs (`QZDASOINIT`) remained alive in **MSGW (Message Wait)** status, waiting for an operator reply to inquiry message `CPA7025` ("Receiver never fully saved"). While waiting, they held locks on the receiver.

2. **`DLTOPT(*IGNINQSG)` is not a valid parameter** on this IBM i version — using it causes an immediate `CPF0006` with no MSGW, no hang. This masked the real problem.

**The fix:** Run `CHGJOB INQMSGRPY(*DFT)` on the **same JDBC connection** before `DLTJRNRCV`. This instructs the AS400 job to auto-answer any inquiry messages (including `CPA7025`) with the default reply (`I` = Ignore/proceed), eliminating the MSGW hang entirely. This is implemented as the `--force` flag in `qadmcli journal cleanup`.

---

## Investigation Timeline

### Phase 1: Identify the Bloated Receiver

**Command:** List all receivers for a journal
```bash
./qadmcli.sh journal receivers -j GSTESTJNR -l GSTESTLIB
```

**Result:**
```
 Receiver   | Status   | Entries   | Size    | Cleanup Status
 GSJNRC0003 | ATTACHED | 48,643    | 0.04 MB | KEEP (Attached)
 GSJNRC0002 | ONLINE   | 5,785,712 | 1.13 MB | Safe to cleanup
```

> [!IMPORTANT]
> `GSJNRC0002` had 5.7M entries and was detached (ONLINE) but could not be deleted.

---

### Phase 2: Attempt Deletion — All Failed with CPF0006

**Attempt 1:** Direct delete with ignore-inquiry option
```bash
./qadmcli.sh sql execute -q "CALL QSYS2.QCMDEXC('DLTJRNRCV JRNRCV(GSTESTLIB/GSJNRC0002) DLTOPT(*IGNINQSG)', 56)"
```
Result: **Immediate `CPF0006`** — no hang, no MSGW.

**Attempt 2:** Journal cleanup via qadmcli (no DLTOPT)
```bash
./qadmcli.sh journal cleanup -j GSTESTJNR -l GSTESTLIB --keep 1
```
Result: **Hung indefinitely** (Ctrl+C'd) — AS400 waiting for `CPA7025` operator reply.

**Attempt 3:** Direct delete without DLTOPT
```bash
./qadmcli.sh sql execute -q "CALL QSYS2.QCMDEXC('DLTJRNRCV JRNRCV(GSTESTLIB/GSJNRC0002)')"
```
Result: **Hung for 36 minutes** in MSGW — `CPA7025` inquiry waiting for reply. Killing the MSGW job (ENDJOB) terminated the connection but did NOT delete the receiver.

**Attempt 4:** Enable auto-delete on the journal
```bash
./qadmcli.sh sql execute -q "CALL QSYS2.QCMDEXC('CHGJRN JRN(GSTESTLIB/GSTESTJNR) DLTRCV(*YES)')"
```
Result: `CPF70E3` — "Only attached receivers allowed in receiver directory." AS400 refuses to enable auto-delete while detached receivers exist.

> [!WARNING]
> **`DLTOPT(*IGNINQSG)` is NOT supported on this IBM i version.** Using it causes an immediate `CPF0006` with no hang. Do not use it. The correct approach is `CHGJOB INQMSGRPY(*DFT)` (see Resolution Playbook).

> [!CAUTION]
> **Never Ctrl+C or ENDJOB the MSGW job** to escape a hung delete. The connection dies but the receiver is NOT deleted. You must either reply to the inquiry or use `CHGJOB INQMSGRPY(*DFT)` before the delete command.

---

### Phase 3: Check Job Log for Detailed Errors

**Command:** View recent job log messages
```bash
./qadmcli.sh sql query -q "SELECT MESSAGE_ID, MESSAGE_TEXT FROM TABLE(QSYS2.JOBLOG_INFO('*')) ORDER BY ORDINAL_POSITION DESC FETCH FIRST 10 ROWS ONLY"
```

> [!NOTE]
> Each `qadmcli` invocation creates a **new JDBC session** (new AS400 job). The job log query only sees messages from the *current* session, not from previous ones. This means you cannot retrieve error details from a previous failed command unless you query that specific job's log (see Phase 5).

---

### Phase 4: Discover Available JOURNAL_INFO Columns

The column names in `QSYS2.JOURNAL_INFO` vary by IBM i version. Several attempts to query `DELETE_RECEIVER`, `MANAGE_RECEIVER`, and `RECEIVER_SIZE_OPTIONS` all failed with `SQL0206` (column not found).

**Command:** List all available columns
```bash
./qadmcli.sh sql query -q "SELECT COLUMN_NAME, DATA_TYPE FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = 'QSYS2' AND TABLE_NAME = 'JOURNAL_INFO' ORDER BY ORDINAL_POSITION"
```

**Actual column names discovered (65 columns total):**

| Expected Column Name | Actual Column Name on This System |
|----------------------|-----------------------------------|
| `MANAGE_RECEIVER` | `MANAGE_RECEIVER_OPTION` |
| `DELETE_RECEIVER` | `DELETE_RECEIVER_OPTION` |
| `RECEIVER_SIZE_OPTIONS` | `RECEIVER_MAXIMUM_SIZE` |

**Correct query for journal settings:**
```bash
./qadmcli.sh sql query -q "SELECT JOURNAL_NAME, MANAGE_RECEIVER_OPTION, DELETE_RECEIVER_OPTION, DELETE_RECEIVER_DELAY, RECEIVER_MAXIMUM_SIZE FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = 'GSTESTLIB' AND JOURNAL_NAME = 'GSTESTJNR'"
```

**Key columns explained:**

| Column | Meaning |
|--------|---------|
| `MANAGE_RECEIVER_OPTION` | `SYSTEM` = auto-rollover when size limit reached; `USER` = manual rollover |
| `DELETE_RECEIVER_OPTION` | `YES` = auto-delete old receivers; `NO` = manual delete required |
| `DELETE_RECEIVER_DELAY` | Days to wait before auto-deleting a detached receiver |
| `MANAGE_RECEIVER_DELAY` | Minutes to wait before auto-rollover |
| `RECEIVER_MAXIMUM_SIZE` | Size threshold triggering rollover (e.g., `MAXOPT2`, `MAXOPT3`) |
| `NUMBER_JOURNAL_RECEIVERS` | Total count of receivers in the chain |
| `TOTAL_SIZE_JOURNAL_RECEIVERS` | Combined size of all receivers (bytes) |

> [!TIP]
> If `SELECT *` from `JOURNAL_INFO` returns garbled output, it's because the table has 65+ columns and the terminal renderer can't fit them. Always query specific columns or use the `SYSCOLUMNS` approach to discover names first.

---

### Phase 5: Find the Lock Holders — QZDASOINIT Jobs

**Command:** List all active JDBC server jobs
```bash
./qadmcli.sh sql query -q "SELECT JOB_NAME, JOB_USER, JOB_STATUS FROM TABLE(QSYS2.ACTIVE_JOB_INFO()) WHERE JOB_NAME LIKE '%QZDASOINIT%'"
```

**Result:** 35 JDBC server jobs found, including **2 in MSGW status**.

> [!NOTE]
> `QSYS2.OBJECT_LOCK_INFO()` does **not exist** on this IBM i version. Use the `ACTIVE_JOB_INFO()` approach instead.

#### Job Status Codes Reference

| Status | Full Name | Meaning | Action Required? |
|--------|-----------|---------|------------------|
| **RUN** | Running | Actively executing | No — normal |
| **MSGW** | Message Wait | ⚠️ Stuck waiting for operator reply | **Yes — likely holding locks** |
| **LCKW** | Lock Wait | Waiting to acquire a lock | Maybe — check what it's waiting on |
| **TIMW** | Time Wait | Idle with timeout | No — normal pooled connection |
| **DEQW** | Dequeue Wait | Idle, waiting for work | No — normal pre-started job |
| **EVTW** | Event Wait | Waiting for event signal | No — normal |
| **PSRW** | Procedure Start Request Wait | Waiting for procedure dispatch | No — normal |

---

### Phase 6: Confirm the Root Cause — MSGW Job Log

**Command:** Check what message a specific MSGW job is waiting on
```bash
./qadmcli.sh sql query -q "SELECT MESSAGE_ID, MESSAGE_TEXT, MESSAGE_TYPE FROM TABLE(QSYS2.JOBLOG_INFO('160938/QUSER/QZDASOINIT')) ORDER BY ORDINAL_POSITION DESC FETCH FIRST 5 ROWS ONLY"
```

**Result:**
```
CPA7025 | Receiver GSJNRCV001 in GSTESTLIB never fully saved. (I C) | SENDER
```

**Explanation:** The job was executing a `DLTJRNRCV` command. The receiver had never been saved (backed up), so the system sent inquiry message `CPA7025` asking the operator to reply:
- **I** = Ignore (proceed with delete anyway)
- **C** = Cancel (abort the delete)

When the user Ctrl+C'd the client, the AS400 job stayed alive waiting for this reply, **holding a lock on the receiver**.

---

## Resolution Playbook

### Step 1: Find and Kill Any Stuck MSGW Jobs

```bash
# Find MSGW jobs (these are holding locks)
./qadmcli.sh sql query -q "SELECT JOB_NAME, JOB_STATUS FROM TABLE(QSYS2.ACTIVE_JOB_INFO()) WHERE JOB_NAME LIKE '%QZDASOINIT%' AND JOB_STATUS = 'MSGW'"

# End each one (replace XXXXXX with job number)
./qadmcli.sh sql execute -q "CALL QSYS2.QCMDEXC('ENDJOB JOB(XXXXXX/QUSER/QZDASOINIT) OPTION(*IMMED)')"
```

Verify all MSGW jobs are gone (0 rows returned).

### Step 2: Delete All Old Receivers Using `--force` ✅

This is the **correct and recommended approach**. The `--force` flag runs `CHGJOB INQMSGRPY(*DFT)` on the same JDBC connection before each delete, which auto-answers the `CPA7025` inquiry with `I` (Ignore/proceed) — no MSGW, no hanging.

```bash
# Dry run first to see what will be deleted
./qadmcli.sh journal cleanup -j GSTESTJNR -l GSTESTLIB --keep 1 --dry-run

# Execute with --force to avoid MSGW hang
./qadmcli.sh journal cleanup -j GSTESTJNR -l GSTESTLIB --keep 1 --force
```

**What happens internally:**
```
CHGJOB INQMSGRPY(*DFT)          ← runs on same JDBC connection
DLTJRNRCV JRNRCV(lib/rcv)        ← CPA7025 auto-answered, no MSGW
CHGJOB INQMSGRPY(*RQD)           ← reset to normal after each delete
```

> [!IMPORTANT]
> The `CHGJOB` and `DLTJRNRCV` **must run on the same JDBC connection** to take effect. This is why separate `qadmcli` commands won't work — each invocation is a new connection.

### Step 3: Verify Cleanup

```bash
./qadmcli.sh journal receivers -j GSTESTJNR -l GSTESTLIB
```

Expected: Only the ATTACHED receiver remains.

### Step 4: Enable Auto-Delete to Prevent Recurrence

Once all detached receivers are removed:
```bash
./qadmcli.sh sql execute -q "CALL QSYS2.QCMDEXC('CHGJRN JRN(GSTESTLIB/GSTESTJNR) DLTRCV(*YES)')"
```

Verify:
```bash
./qadmcli.sh sql query -q "SELECT JOURNAL_NAME, DELETE_RECEIVER_OPTION, DELETE_RECEIVER_DELAY FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = 'GSTESTLIB' AND JOURNAL_NAME = 'GSTESTJNR'"
```

### Confirmed Working — Actual Session Output

```
# Rollover to detach the bloated receiver
./qadmcli.sh journal rollover -l GSTESTLIB -j GSTESTJNR
  Old receiver: GSJNRC0003 (now ONLINE)
  New receiver: GSJNRC0004 (now ATTACHED)

# Delete with --force
./qadmcli.sh journal cleanup -j GSTESTJNR -l GSTESTLIB --keep 1 --force
  Force mode: auto-answering 'receiver not saved' inquiry (CPA7025)
  Deleted receiver: GSJNRC0002 ✅  (5,785,712 entries, 1.13 MB freed)
  Cleanup complete: 1 deleted, 0 failed
```

---

## Quick Reference: Common CL Commands via QCMDEXC

| Task | Command |
|------|---------|
| **Rollover journal** | `./qadmcli.sh journal rollover -j jrn -l lib` |
| **List receivers** | `./qadmcli.sh journal receivers -j jrn -l lib` |
| **Cleanup (safe)** | `./qadmcli.sh journal cleanup -j jrn -l lib --keep 1 --dry-run` |
| **Cleanup (force)** ⭐ | `./qadmcli.sh journal cleanup -j jrn -l lib --keep 1 --force` |
| **Find MSGW jobs** | `SELECT JOB_NAME FROM TABLE(QSYS2.ACTIVE_JOB_INFO()) WHERE JOB_NAME LIKE '%QZDASOINIT%' AND JOB_STATUS = 'MSGW'` |
| **Kill stuck job** | `CALL QSYS2.QCMDEXC('ENDJOB JOB(number/user/name) OPTION(*IMMED)')` |
| **Check job log** | `SELECT MESSAGE_ID, MESSAGE_TEXT FROM TABLE(QSYS2.JOBLOG_INFO('number/user/name')) ORDER BY ORDINAL_POSITION DESC FETCH FIRST 10 ROWS ONLY` |
| **Find journaled tables** | `SELECT OBJECT_LIBRARY, OBJECT_NAME, OBJECT_TYPE FROM QSYS2.JOURNALED_OBJECTS WHERE JOURNAL_LIBRARY = 'lib' AND JOURNAL_NAME = 'jrn'` |
| **Enable auto-delete** | `CALL QSYS2.QCMDEXC('CHGJRN JRN(lib/jrn) DLTRCV(*YES)')` |
| **Enable auto-manage** | `CALL QSYS2.QCMDEXC('CHGJRN JRN(lib/jrn) MNGRCV(*SYSTEM)')` |
| **Journal settings** | `SELECT JOURNAL_NAME, MANAGE_RECEIVER_OPTION, DELETE_RECEIVER_OPTION FROM QSYS2.JOURNAL_INFO WHERE JOURNAL_LIBRARY = 'lib' AND JOURNAL_NAME = 'jrn'` |
| **Discover columns** | `SELECT COLUMN_NAME FROM QSYS2.SYSCOLUMNS WHERE TABLE_SCHEMA = 'QSYS2' AND TABLE_NAME = 'viewname'` |

---

## Lessons Learned

> [!CAUTION]
> **Never Ctrl+C or ENDJOB a hung `DLTJRNRCV`** — the connection dies but the receiver is NOT deleted, and future attempts will be blocked by a new MSGW lock. Always use `--force` or handle the inquiry properly.

> [!TIP]
> **Use `journal cleanup --force`** for all receiver deletions on this system. It is the only reliable approach because `DLTOPT(*IGNINQSG)` is not supported on this IBM i version.

> [!WARNING]
> **`DLTOPT(*IGNINQSG)` is NOT supported on this IBM i version.** It causes an immediate `CPF0006` with no MSGW. The equivalent fix is `CHGJOB INQMSGRPY(*DFT)` on the same JDBC connection before the delete.

> [!TIP]
> **Always check for MSGW jobs** before any delete attempt. Run: `SELECT JOB_NAME FROM TABLE(QSYS2.ACTIVE_JOB_INFO()) WHERE JOB_NAME LIKE '%QZDASOINIT%' AND JOB_STATUS = 'MSGW'`. Kill them first, then run cleanup with `--force`.

> [!IMPORTANT]
> **Column names in QSYS2 views vary by IBM i version.** Always use `QSYS2.SYSCOLUMNS` to discover actual column names. Key differences on this system: `DELETE_RECEIVER_OPTION` (not `DELETE_RECEIVER`), `MANAGE_RECEIVER_OPTION` (not `MANAGE_RECEIVER`).

> [!NOTE]
> **`QSYS2.OBJECT_LOCK_INFO()` does not exist on this IBM i version.** Use `ACTIVE_JOB_INFO()` filtered to `QZDASOINIT` jobs with `MSGW` status as the lock diagnostic approach instead.

> [!NOTE]
> **To find which tables use a specific journal**, query `QSYS2.JOURNALED_OBJECTS` (not `SYSTABLES` or `SYSPARTITIONSTAT` — neither has journal columns on this system):
> ```sql
> SELECT OBJECT_LIBRARY, OBJECT_NAME, OBJECT_TYPE, JOURNAL_IMAGES
> FROM QSYS2.JOURNALED_OBJECTS
> WHERE JOURNAL_LIBRARY = 'GSTESTLIB' AND JOURNAL_NAME = 'GSTESTJNR'
> ```
