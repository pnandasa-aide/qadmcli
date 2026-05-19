# DB2 for i CCSID Encoding: Complete Guide

## Overview

This document explains how CCSID (Coded Character Set Identifier) encoding works in DB2 for i, including the complete data flow from client input to storage and retrieval.

---

## What is CCSID?

**CCSID (Coded Character Set Identifier)** is IBM's system for identifying character encodings. Each CCSID value represents a specific character set and encoding method.

### **Common CCSID Values:**

| CCSID | Encoding Name | Description | Thai Support |
|-------|--------------|-------------|--------------|
| **1208** | UTF-8 | Unicode UTF-8 | ✅ Yes (all Unicode) |
| **838** | Thai EBCDIC | IBM Thai EBCDIC | ✅ Yes |
| **37** | US English EBCDIC | IBM US/Canada EBCDIC | ❌ No |
| **65535** | Binary | Raw bytes (no conversion) | ⚠️ Raw bytes only |

---

## Complete Data Flow

### **INSERT Process (Storing Data)**

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: User Input (DBeaver / Java Application)                │
├─────────────────────────────────────────────────────────────────┤
│ Input: 'สมชาย' (Thai characters)                                │
│ Internal Encoding: UTF-16 (Java String)                        │
│ Code Points: U+0E2A U+0E21 U+0E0A U+0E32 U+0E22               │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: JT400 JDBC Driver                                       │
├─────────────────────────────────────────────────────────────────┤
│ Receives: Java String "สมชาย" (UTF-16)                          │
│ Converts: UTF-16 → UTF-8 bytes                                  │
│   UTF-8 Bytes: E0 B8 AA E0 B8 A1 E0 B8 8A E0 B8 B2 E0 B8 A2    │
│                                                                 │
│ Checks: Target column CCSID = 838 (Thai EBCDIC)                │
│ Converts: UTF-8 → CCSID 838 (Thai EBCDIC)                      │
│   EBCDIC Bytes: D9 E2 4B E2 6C 4B E2 A2                        │
│                                                                 │
│ Sends to DB2: CCSID 838 bytes                                  │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: DB2 for i Storage                                       │
├─────────────────────────────────────────────────────────────────┤
│ Receives: CCSID 838 bytes from JT400                           │
│ Stores on disk: D9 E2 4B E2 6C 4B E2 A2 (CCSID 838 format)    │
│ Metadata: Column tagged with CCSID 838                         │
│                                                                 │
│ NO additional conversion - stores exactly as received          │
└─────────────────────────────────────────────────────────────────┘
```

---

### **RETRIEVAL Process (Reading Data)**

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: DB2 for i Read                                          │
├─────────────────────────────────────────────────────────────────┤
│ Reads from disk: D9 E2 4B E2 6C 4B E2 A2 (CCSID 838 bytes)    │
│ Column metadata: CCSID 838                                     │
│ Sends to JT400: CCSID 838 bytes                                │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: JT400 JDBC Driver                                       │
├─────────────────────────────────────────────────────────────────┤
│ Receives: CCSID 838 bytes                                      │
│ Converts: CCSID 838 → UTF-8                                    │
│   UTF-8 Bytes: E0 B8 AA E0 B8 A1 E0 B8 8A E0 B8 B2 E0 B8 A2    │
│                                                                 │
│ Converts: UTF-8 → Java String (UTF-16)                         │
│   Returns: "สมชาย" (Java String object)                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: DBeaver Display                                         │
├─────────────────────────────────────────────────────────────────┤
│ Receives: Java String "สมชาย"                                   │
│ Renders: สมชาย (using system Thai font)                         │
│ User sees: Thai characters correctly displayed                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Concept: JT400 Automatic Conversion

**JT400 JDBC driver handles ALL CCSID conversions automatically.**

### **What This Means:**

1. ✅ **You work with Java Strings** - always UTF-16 internally
2. ✅ **JT400 converts to target CCSID** on INSERT/UPDATE
3. ✅ **JT400 converts from source CCSID** on SELECT
4. ✅ **You never see EBCDIC bytes** - only Java Strings

### **Example Code:**

```java
// INSERT - You provide Java String
PreparedStatement stmt = conn.prepareStatement(
    "INSERT INTO THAI_TEST (FIRSTNAME_TH) VALUES (?)"
);

stmt.setString(1, "สมชาย");  // Java String (UTF-16)
stmt.executeUpdate();

// JT400 automatically:
// 1. Converts UTF-16 → UTF-8
// 2. Converts UTF-8 → CCSID 838 (Thai EBCDIC)
// 3. Sends CCSID 838 bytes to DB2

// SELECT - You get Java String back
ResultSet rs = stmt.executeQuery("SELECT FIRSTNAME_TH FROM THAI_TEST");
String name = rs.getString("FIRSTNAME_TH");

// JT400 automatically:
// 1. Receives CCSID 838 bytes from DB2
// 2. Converts CCSID 838 → UTF-8
// 3. Converts UTF-8 → UTF-16 Java String
// 4. Returns: "สมชาย"
```

---

## CCSID Encoding Examples

### **Character: "สม" (Thai characters)**

| CCSID | Encoding | Bytes | Length |
|-------|----------|-------|--------|
| **UTF-16** (Java String) | UTF-16BE | `0E 2A 0E 21` | 4 bytes |
| **UTF-8** (CCSID 1208) | UTF-8 | `E0 B8 AA E0 B8 A1` | 4 bytes |
| **Thai EBCDIC** (CCSID 838) | EBCDIC | `D9 E2 4B E2` | 4 bytes |
| **English EBCDIC** (CCSID 37) | N/A | ❌ Cannot encode | N/A |

### **Character: "John" (English)**

| CCSID | Encoding | Bytes | Length |
|-------|----------|-------|--------|
| **UTF-16** (Java String) | UTF-16BE | `00 4A 00 6F 00 68 00 6E` | 8 bytes |
| **UTF-8** (CCSID 1208) | UTF-8 | `4A 6F 68 6E` | 4 bytes |
| **English EBCDIC** (CCSID 37) | EBCDIC | `D1 96 88 95` | 4 bytes |
| **Thai EBCDIC** (CCSID 838) | EBCDIC | `D1 96 88 95` | 4 bytes |

---

## How to Check Column CCSID

### **Method 1: Using qadmcli**

```bash
cd /home/ubuntu/_qoder/qadmcli
sudo -E bash qadmcli.sh table check -l GSLIBTST -t THAI_TEST
```

**Output:**

```
Columns in GSLIBTST.THAI_TEST
┌──────────────────┬─────────────┬────────┬──────────┬──────────┬───────────────┬─────────────────┐
│ Column           │ Type        │ Length │ Nullable │ Identity │ CCSID         │ Mockup Pattern  │
├──────────────────┼─────────────┼────────┼──────────┼──────────┼───────────────┼─────────────────┤
│ ID               │ INTEGER     │ 4      │ No       │          │               │ integer         │
│ FIRSTNAME_TH     │ VARCHAR     │ 50     │ Yes      │          │ 838 (Thai)    │ thai_first_name │
│ LASTNAME_TH      │ VARCHAR     │ 50     │ Yes      │          │ 838 (Thai)    │ thai_last_name  │
│ STORE_ID         │ CHAR        │ 10     │ Yes      │          │ 65535 (Binary)│ binary          │
│ STORE_ID_EBCDIC  │ CHAR        │ 10     │ Yes      │          │ 37 (English)  │ string          │
│ RAW_DATA         │ VARCHAR     │ 50     │ Yes      │          │ 65535 (Binary)│ binary          │
│ FULLNAME_TH      │ VARCHAR     │ 100    │ Yes      │          │ 838 (Thai)    │ thai_full_name  │
└──────────────────┴─────────────┴────────┴──────────┴──────────┴───────────────┴─────────────────┘
```

---

### **Method 2: Direct SQL Query**

```sql
-- Query CCSID for all columns in a table
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    LENGTH,
    CCSID,
    CASE CCSID
        WHEN 838 THEN 'Thai EBCDIC'
        WHEN 1208 THEN 'UTF-8'
        WHEN 37 THEN 'English EBCDIC'
        WHEN 65535 THEN 'Binary'
        WHEN 0 THEN 'Default (Job CCSID)'
        ELSE 'Other (' || CHAR(CCSID) || ')'
    END as CCSID_DESCRIPTION
FROM QSYS2.SYSCOLUMNS
WHERE SYSTEM_TABLE_NAME = 'THAI_TEST'
  AND SYSTEM_TABLE_SCHEMA = 'GSLIBTST'
ORDER BY ORDINAL_POSITION;
```

---

### **Method 3: JSON Output**

```bash
sudo -E bash qadmcli.sh table check -l GSLIBTST -t THAI_TEST --format json
```

**Output:**

```json
{
  "columns": [
    {
      "name": "FIRSTNAME_TH",
      "type": "VARCHAR",
      "length": 50,
      "ccsid": 838,
      "is_binary": false
    },
    {
      "name": "STORE_ID",
      "type": "CHAR",
      "length": 10,
      "ccsid": 65535,
      "is_binary": true
    }
  ]
}
```

---

## CCSID Behavior by Type

### **Character Columns (VARCHAR, CHAR)**

| CCSID | Behavior | Use Case |
|-------|----------|----------|
| **838** | Stores Thai EBCDIC, auto-converts UTF-8 input | Thai text |
| **1208** | Stores UTF-8 directly | Multi-language text |
| **37** | Stores English EBCDIC only | English text |
| **65535** | Stores raw bytes (no conversion) | Binary data |

### **Binary Columns (FOR BIT DATA, BLOB)**

- Always use **CCSID 65535**
- **NO character conversion** - bytes stored as-is
- Use `X'HEXSTRING'` syntax for literals

```sql
-- Binary literal syntax
INSERT INTO BINARY_TEST (TOKEN) 
VALUES (X'A3F7B2E9D1C40582');
```

---

## Common Issues and Solutions

### **Issue 1: Thai Characters Display as Garbage**

**Cause:** Column has wrong CCSID (e.g., CCSID 37 instead of 838)

**Solution:**
```sql
-- Check current CCSID
SELECT CCSID FROM QSYS2.SYSCOLUMNS 
WHERE SYSTEM_TABLE_NAME = 'THAI_TEST' 
  AND COLUMN_NAME = 'FIRSTNAME_TH';

-- If CCSID is wrong, recreate column with correct CCSID
ALTER TABLE THAI_TEST 
ALTER COLUMN FIRSTNAME_TH SET DATA TYPE VARCHAR(50) CCSID 838;
```

---

### **Issue 2: Cannot Insert Thai Characters**

**Cause:** Column CCSID doesn't support Thai (e.g., CCSID 37)

**Symptoms:**
```
Error: SQL0802 - Data conversion or data mapping error
```

**Solution:** Change column CCSID to 838 or 1208

---

### **Issue 3: Binary Data Gets Corrupted**

**Cause:** Column has character CCSID instead of 65535

**Solution:** Use CCSID 65535 for binary columns

```sql
-- Create binary column
CREATE TABLE BINARY_TEST (
    TOKEN VARCHAR(64) CCSID 65535  -- Binary data
);

-- Or use FOR BIT DATA syntax
CREATE TABLE BINARY_TEST (
    TOKEN VARCHAR(64) FOR BIT DATA  -- Binary data
);
```

---

## Best Practices

### **1. Use CCSID 838 for Thai Text**

```sql
CREATE TABLE THAI_TEST (
    FIRSTNAME_TH VARCHAR(50) CCSID 838,  -- ✅ Thai text
    LASTNAME_TH VARCHAR(50) CCSID 838    -- ✅ Thai text
);
```

### **2. Use CCSID 1208 for Multi-Language**

```sql
CREATE TABLE MULTI_LANG (
    NAME VARCHAR(100) CCSID 1208  -- ✅ Supports all Unicode
);
```

### **3. Use CCSID 65535 for Binary Data**

```sql
CREATE TABLE BINARY_DATA (
    TOKEN VARCHAR(64) CCSID 65535,      -- ✅ Binary
    HASH CHAR(32) FOR BIT DATA          -- ✅ Binary (alternative syntax)
);
```

### **4. Never Use CCSID 37 for Thai**

```sql
-- ❌ WRONG - Cannot store Thai characters
CREATE TABLE WRONG (
    NAME VARCHAR(50) CCSID 37  -- English only!
);
```

---

## JT400 Driver Configuration

### **Default Behavior:**

JT400 automatically detects target column CCSID and performs conversion.

### **Connection String:**

```java
// Default: Automatic CCSID conversion
String url = "jdbc:as400://161.82.146.249;translate binary=true";

// translate binary=true: Required for CCSID 65535 columns
```

### **Key Properties:**

| Property | Default | Description |
|----------|---------|-------------|
| `translate binary` | `false` | Enable binary data transfer |
| `character encoding` | Auto | Override default encoding |
| ` CCSID` | Auto | Override default CCSID |

---

## Testing CCSID Configuration

### **Test 1: Insert and Retrieve Thai Text**

```sql
-- Insert Thai text
INSERT INTO THAI_TEST (ID, FIRSTNAME_TH) 
VALUES (12345, 'สมชาย');

-- Retrieve (should display Thai correctly)
SELECT FIRSTNAME_TH FROM THAI_TEST WHERE ID = 12345;
-- Expected: สมชาย
```

### **Test 2: Insert and Retrieve Binary Data**

```sql
-- Insert binary data
INSERT INTO BINARY_TEST (ID, TOKEN) 
VALUES (12345, X'A3F7B2E9D1');

-- Retrieve as hex
SELECT 
    TOKEN,
    HEX(TOKEN) as TOKEN_HEX 
FROM BINARY_TEST WHERE ID = 12345;
-- Expected: A3F7B2E9D1
```

---

## Summary

| Aspect | Key Point |
|--------|-----------|
| **CCSID 838** | Thai EBCDIC - stores Thai characters |
| **CCSID 1208** | UTF-8 - stores all Unicode characters |
| **CCSID 65535** | Binary - no character conversion |
| **JT400 Driver** | Handles ALL CCSID conversions automatically |
| **Java Strings** | Always UTF-16 internally |
| **Storage** | DB2 stores in column's CCSID format |
| **Retrieval** | JT400 converts back to UTF-16 Java String |
| **Check CCSID** | Use `qadmcli table check` or query `QSYS2.SYSCOLUMNS` |

---

## References

- **IBM CCSID Documentation:** https://www.ibm.com/docs/en/i/7.4?topic=reference-coded-character-set-identifiers
- **JT400 Driver Guide:** https://www.ibm.com/docs/en/i/7.4?topic=jdbc-toolbox-driver
- **qadmcli Documentation:** `~/qadmcli/docs/`
- **Related Files:**
  - `/qadmcli/src/qadmcli/db/mockup.py` - CCSID-aware data generation
  - `/qadmcli/src/qadmcli/utils/data_generator.py` - Thai character support
  - `/qadmcli/docs/CCSID-AWARE-MOCKUP.md` - CCSID mockup generation

---

**Last Updated:** 2026-05-05  
**Version:** 1.0
