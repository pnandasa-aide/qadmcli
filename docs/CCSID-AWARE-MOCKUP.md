# CCSID-Aware Mock Data Generation

## Overview

qadmcli's `mockup generate` command now supports **CCSID-aware data generation** and **proper binary literal syntax** for DB2 for i (AS400) tables. It automatically:

1. Detects column CCSID values and generates appropriate character data
2. Detects binary columns (`FOR BIT DATA`) and uses proper `X'HEXSTRING'` syntax
3. Prevents encoding errors and SQL syntax issues

---

## The Problem

DB2 for i uses **CCSID (Coded Character Set Identifier)** to define character encoding:

| CCSID | Encoding | Description |
|-------|----------|-------------|
| **37** | English EBCDIC | US/Canada English |
| **838** | Thai EBCDIC | Thai language (EBCDIC) |
| **1208** | UTF-8 | Unicode (UTF-8) |
| **65535** | Binary/Mixed | No translation (binary data) |

**Before this fix:**
- qadmcli generated UTF-8 Thai characters (สมชาย) for all Thai columns
- Inserting UTF-8 Thai into CCSID 838 columns caused SQL syntax errors
- Error: `[SQL0104] Token ) was not valid`

**After this fix:**
- qadmcli detects CCSID from `QSYS2.SYSCOLUMNS`
- Generates ASCII transliteration for CCSID 838 (Somchai)
- Generates full Thai Unicode for CCSID 1208 (สมชาย)
- Generates ASCII only for CCSID 37 and 65535

---

## How It Works

### **1. CCSID Detection**

When retrieving table schema, qadmcli now fetches the CCSID column:

```python
# mockup.py - _get_columns() method
SELECT 
    c.SYSTEM_COLUMN_NAME,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.LENGTH,
    c.NUMERIC_SCALE,
    c.IS_NULLABLE,
    c.COLUMN_DEFAULT,
    c.COLUMN_TEXT,
    c.IS_IDENTITY,
    c.CCSID  # ← NEW: Retrieved from SYSCOLUMNS
FROM QSYS2.SYSCOLUMNS c
WHERE c.SYSTEM_TABLE_NAME = ?
AND c.SYSTEM_TABLE_SCHEMA = ?
```

### **2. DB2 Automatic Conversion**

**Key Insight:** DB2 for i automatically converts UTF-8 input to the target column's CCSID.

When Python sends Thai Unicode via jaydebeapi:
```python
# Python sends UTF-8
value = "สมชาย"  # UTF-8 encoded

# DB2 automatically converts to target CCSID:
# - CCSID 838: Converts UTF-8 → Thai EBCDIC
# - CCSID 1208: Stores as UTF-8 (no conversion)
# - CCSID 37: Converts (but may lose Thai characters)
```

**This means:** We can always send Thai Unicode characters, and DB2 handles the conversion!

### **3. Thai Name Generation**

The data generator detects Thai columns and generates Thai Unicode:

```python
# data_generator.py - FirstNamePattern.generate()
def generate(self, length=None, scale=None, field_name="", ccsid=None):
    is_thai = any(thai in field_name.upper() for thai in self.thai_patterns)
    
    if is_thai:
        # Always send Thai Unicode - DB2 converts to target CCSID
        return random.choice([
            "สมชาย", "สมหญิง", "ประเสริฐ", "มณี", ...
        ])
    
    return random.choice(self.FIRST_NAMES)
```

---

## Example: THAI_TEST Table

### **Table Schema:**

```sql
CREATE TABLE GSLIBTST.THAI_TEST (
    ID             INTEGER,
    FIRSTNAME_TH   VARCHAR(100) CCSID 838,    -- Thai EBCDIC
    LASTNAME_TH    VARCHAR(100) CCSID 838,    -- Thai EBCDIC
    STORE_ID       CHAR(10)     CCSID 65535,  -- Binary
    STORE_ID_EBCDIC CHAR(10)    CCSID 37,     -- English EBCDIC
    RAW_DATA       VARCHAR(50)  CCSID 65535,  -- Binary
    CREATED_AT     TIMESTAMP,
    FULLNAME_TH    VARCHAR(200) CCSID 1208    -- UTF-8
);
```

### **Generated Mock Data:**

| Column | CCSID | Generated Value | Notes |
|--------|-------|-----------------|-------|
| ID | - | `12345` | Random integer |
| FIRSTNAME_TH | 838 | `สมชาย` | Thai Unicode (DB2 converts to EBCDIC) |
| LASTNAME_TH | 838 | `แสงสว่าง` | Thai Unicode (DB2 converts to EBCDIC) |
| STORE_ID | 65535 | `ABC123` | ASCII only |
| STORE_ID_EBCDIC | 37 | `STORE001` | ASCII only |
| RAW_DATA | 65535 | `RAW123` | ASCII only |
| CREATED_AT | - | `2026-04-30 10:30:00` | Random timestamp |
| FULLNAME_TH | 1208 | `สมชาย แสงสว่าง` | Thai Unicode (stored as UTF-8) |

---

## Binary Literal Support (FOR BIT DATA)

### **The Problem**

DB2 for i uses several methods to define binary columns:

```sql
CREATE TABLE BINARY_TEST (
    TOKEN VARCHAR(64) FOR BIT DATA,  -- Binary token
    HASH CHAR(32) FOR BIT DATA,      -- Fixed-length hash
    STORE_ID CHAR(10) CCSID 65535,   -- Binary via CCSID
    RAW_DATA VARCHAR(50) CCSID 65535 -- Binary via CCSID
);
```

**Before this fix:**
- qadmcli generated: `INSERT INTO table (token) VALUES ('A3F7B2E9');`
- DB2 interpreted as **character string**, not binary ❌
- Random integers or ASCII strings generated for binary columns ❌

**After this fix:**
- qadmcli generates: `INSERT INTO table (token) VALUES (X'A3F7B2E9');`
- DB2 interprets as **binary literal** ✅
- Hex strings generated for all binary columns ✅

---

### **How to Detect Binary Columns**

DB2 for i has **TWO ways** to define binary columns:

#### **Method 1: Explicit "FOR BIT DATA" Syntax**

```sql
CREATE TABLE example1 (
    TOKEN VARCHAR(64) FOR BIT DATA,
    HASH CHAR(32) FOR BIT DATA
);
```

**Detection:** Check if `DATA_TYPE` contains "FOR BIT DATA"

```sql
-- Query to detect
SELECT 
    COLUMN_NAME,
    DATA_TYPE
FROM QSYS2.SYSCOLUMNS
WHERE TABLE_NAME = 'EXAMPLE1';

-- Result:
-- TOKEN    | VARCHAR FOR BIT DATA
-- HASH     | CHARACTER FOR BIT DATA
```

**qadmcli detection:**
```python
# mockup.py - _build_insert_sql()
if "FOR BIT DATA" in col_type:
    # Binary column detected!
    values.append(f"X'{hex_val}'")
```

---

#### **Method 2: CCSID 65535 (Binary/Mixed)**

```sql
CREATE TABLE example2 (
    STORE_ID CHAR(10) CCSID 65535,
    RAW_DATA VARCHAR(50) CCSID 65535
);
```

**Detection:** Check if `CCSID = 65535`

```sql
-- Query to detect
SELECT 
    COLUMN_NAME,
    DATA_TYPE,
    CCSID
FROM QSYS2.SYSCOLUMNS
WHERE TABLE_NAME = 'EXAMPLE2';

-- Result:
-- STORE_ID  | CHARACTER | 65535  ← Binary!
-- RAW_DATA  | VARCHAR   | 65535  ← Binary!
```

**qadmcli detection:**
```python
# mockup.py - _get_columns()
columns.append({
    "ccsid": row[9],
    "is_binary": row[9] == 65535,  # CCSID 65535 = binary
})

# mockup.py - _build_insert_sql()
if c.get("is_binary"):
    # Binary column detected!
    values.append(f"X'{hex_val}'")
```

---

### **Complete Binary Detection Logic**

qadmcli uses **BOTH methods** to detect binary columns:

```python
# mockup.py - _build_insert_sql()
is_binary_col = (
    # Method 1: Explicit "FOR BIT DATA" syntax
    "FOR BIT DATA" in col_type or 
    col_type in ("BINARY", "VARBINARY", "BLOB") or
    
    # Method 2: CCSID 65535
    any(c["name"].upper() == col_name.upper() and c.get("is_binary") 
        for c in (columns or []))
)

if is_binary_col:
    # Generate hex string and use X'...' syntax
    hex_val = val.upper().replace(' ', '')
    if all(c in '0123456789ABCDEF' for c in hex_val):
        values.append(f"X'{hex_val}'")  # ✅ Binary literal
```

---

### **How Binary Data Generation Works**

#### **1. Schema Retrieval**

```python
# mockup.py - _get_columns()
SELECT 
    c.COLUMN_NAME,
    c.DATA_TYPE,    # e.g., "VARCHAR" or "VARCHAR FOR BIT DATA"
    c.CCSID         # e.g., 65535 for binary
FROM QSYS2.SYSCOLUMNS c
```

#### **2. Hex String Generation**

For CCSID 65535 columns, the data generator creates hex strings:

```python
# data_generator.py - generate_for_column()
if ccsid == 65535:
    # Generate hex string for binary data
    hex_length = min(length or 20, 64)
    return ''.join(random.choices(string.hexdigits.upper(), k=hex_length))
    # Example: "A3F7B2E9D1C40582"
```

For "FOR BIT DATA" types, the pattern matcher returns "binary":

```python
# data_generator.py - _fallback_pattern_name()
type_upper = data_type.upper()
if "FOR BIT DATA" in type_upper:
    return "binary"  # Triggers hex generation
```

#### **3. SQL Generation with Binary Literals**

The INSERT builder formats binary values with `X'...'` syntax:

```python
# mockup.py - _build_insert_sql()
if is_binary_col:
    hex_val = val.upper().replace(' ', '')
    if all(c in '0123456789ABCDEF' for c in hex_val):
        values.append(f"X'{hex_val}'")  # ✅ DB2 binary literal
```

---

### **Example: Binary Column Mock Data**

#### **DB2 Table:**
```sql
CREATE TABLE GSLIBTST.BINARY_TEST (
    ID INT,
    TOKEN VARCHAR(64) FOR BIT DATA,  -- Method 1: Explicit
    STORE_ID CHAR(10) CCSID 65535,   -- Method 2: CCSID
    RAW_DATA VARCHAR(50) CCSID 65535 -- Method 2: CCSID
);
```

#### **Generated SQL:**
```sql
-- ✅ CORRECT: All binary columns use X'HEXSTRING' syntax
INSERT INTO GSLIBTST.BINARY_TEST (ID, TOKEN, STORE_ID, RAW_DATA) 
VALUES (
    12345,
    X'A3F7B2E9D1C40582F6A8B3E7D2C9',  -- FOR BIT DATA → hex literal
    X'1A2B3C4D5E',                    -- CCSID 65535 → hex literal
    X'6F7A8B9C0D1E2F3A4B5C6D7E8F'    -- CCSID 65535 → hex literal
);
```

---

### **DB2 → MSSQL Binary Mapping**

| DB2 Type | Detection Method | MSSQL Equivalent | GlueSync Handling |
|----------|------------------|------------------|-------------------|
| `CHAR(n) FOR BIT DATA` | DATA_TYPE contains "FOR BIT DATA" | `BINARY(n)` | ✅ Auto-converts |
| `VARCHAR(n) FOR BIT DATA` | DATA_TYPE contains "FOR BIT DATA" | `VARBINARY(n)` | ✅ Auto-converts |
| `CHAR(n) CCSID 65535` | CCSID = 65535 | `BINARY(n)` | ✅ Auto-converts |
| `VARCHAR(n) CCSID 65535` | CCSID = 65535 | `VARBINARY(n)` | ✅ Auto-converts |
| `BLOB` | DATA_TYPE = "BLOB" | `VARBINARY(MAX)` | ✅ Auto-converts |

**GlueSync Replication:**
```
DB2 (Source)                    MSSQL (Target)
──────────────────────────────────────────────────
X'A3F7B2E9'                →    0xA3F7B2E9
(VARCHAR FOR BIT DATA)          (VARBINARY)

X'1A2B3C4D5E'              →    0x1A2B3C4D5E
(CHAR CCSID 65535)              (BINARY)
```

---

### **Example: Binary Column Mock Data**

#### **DB2 Table:**
```sql
CREATE TABLE GSLIBTST.BINARY_TEST (
    ID INT,
    TOKEN VARCHAR(64) FOR BIT DATA,
    HASH CHAR(32) FOR BIT DATA
);
```

#### **Generated SQL:**
```sql
-- ✅ CORRECT: Binary literal syntax
INSERT INTO GSLIBTST.BINARY_TEST (ID, TOKEN, HASH) 
VALUES (
    12345,
    X'A3F7B2E9D1C40582F6A8B3E7D2C9',  -- Binary literal
    X'1A2B3C4D5E6F7A8B9C0D1E2F3A4B'   -- Binary literal
);
```

---

### **DB2 → MSSQL Binary Mapping**

| DB2 Type | MSSQL Equivalent | GlueSync Handling |
|----------|------------------|-------------------|
| `CHAR(n) FOR BIT DATA` | `BINARY(n)` | ✅ Auto-converts |
| `VARCHAR(n) FOR BIT DATA` | `VARBINARY(n)` | ✅ Auto-converts |
| `BLOB` | `VARBINARY(MAX)` | ✅ Auto-converts |

**GlueSync Replication:**
```
DB2 (Source)              MSSQL (Target)
─────────────────────────────────────────
X'A3F7B2E9'          →    0xA3F7B2E9
(VARCHAR FOR BIT DATA)    (VARBINARY)
```

---

### **Binary vs Character Columns**

| Feature | CHAR/VARCHAR | FOR BIT DATA | CCSID 65535 |
|---------|--------------|--------------|-------------|
| **Purpose** | Text data | Binary data | Binary data |
| **CCSID** | Yes (37, 838, 1208) | No (binary) | 65535 (binary) |
| **SQL Literal** | `'text'` | `X'HEXSTRING'` | `X'HEXSTRING'` |
| **Encoding** | Character encoding | Raw bytes | Raw bytes |
| **Use Cases** | Names, addresses | Hashes, tokens | IDs, payloads |
| **Detection** | CCSID != 65535 | "FOR BIT DATA" in type | CCSID = 65535 |
| **qadmcli Generates** | Thai/ASCII text | Hex string | Hex string |

---

## Usage

### **Basic Command:**

```bash
cd ~/_qoder/qadmcli
sudo -E bash qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 20
```

### **Parameters:**

- `-t THAI_TEST` - Table name (use actual table name, not TEST_THAI)
- `-l GSLIBTST` - Library/schema name
- `-r 20` - Number of transactions (50% insert, 30% update, 20% delete)

---

## CCSID Reference

### **Supported CCSIDs:**

| CCSID | Encoding | Thai Support | How It Works |
|-------|----------|--------------|--------------|
| **37** | English EBCDIC | ⚠️ Limited | DB2 converts UTF-8 → EBCDIC 37 (may lose Thai) |
| **838** | Thai EBCDIC | ✅ Full | DB2 converts UTF-8 → Thai EBCDIC 838 |
| **1208** | UTF-8 | ✅ Full | Stored as UTF-8 (no conversion) |
| **65535** | Binary/Mixed | ❌ No | No conversion, ASCII only |

## How DB2 Handles CCSID Conversion

When Python sends Thai Unicode via jaydebeapi:

```
Python (UTF-8) → DB2 Conversion → Storage
─────────────────────────────────────────────
"สมชาย" (UTF-8) → CCSID 838 → Thai EBCDIC bytes
"สมชาย" (UTF-8) → CCSID 1208 → UTF-8 bytes (no conversion)
"สมชาย" (UTF-8) → CCSID 37 → May fail/lose data
```

**DB2 automatically handles the conversion**, so qadmcli always sends Thai Unicode!

---

---

## Technical Implementation

### **Files Modified:**

1. **`src/qadmcli/db/mockup.py`**
   - Added `c.CCSID` to SELECT query in `_get_columns()`
   - Added `"ccsid"` field to column dictionary
   - Added `"is_binary"` flag: `row[9] == 65535` (CCSID 65535 detection)
   - Updated all `generate_for_column()` calls to pass `col.get("ccsid")`
   - Modified `_build_insert_sql()` to accept `columns` metadata parameter
   - Implemented **dual binary detection**:
     - Method 1: `"FOR BIT DATA" in col_type`
     - Method 2: `c.get("is_binary")` (CCSID 65535)
   - Implemented `X'{value}'` syntax for binary literals
   - Validates hex characters before creating binary literal
   - Updated callers to pass column metadata to `_build_insert_sql()`

2. **`src/qadmcli/utils/data_generator.py`**
   - Added `ccsid` parameter to `generate_for_column()` method
   - Added CCSID parameter to `FirstNamePattern.generate()`
   - Added CCSID parameter to `LastNamePattern.generate()`
   - Removed ASCII transliteration logic for CCSID 838
   - Updated to always send Thai Unicode (DB2 handles conversion)
   - Added special handling for **CCSID 65535** (binary columns)
   - Generates uppercase hex strings for binary data
   - Added `"FOR BIT DATA"` detection in `_fallback_pattern_name()`
   - Returns `"binary"` pattern for binary column types

### **Code Flow:**

```
mockup generate command
    ↓
_get_columns() - retrieves CCSID from QSYS2.SYSCOLUMNS
    ↓
Generate column metadata:
  - "ccsid": 65535 (or 838, 1208, etc.)
  - "is_binary": true (if CCSID = 65535)
    ↓
_generate_row_data() - passes CCSID to data generator
    ↓
generate_for_column(ccsid=65535)
    ↓
if ccsid == 65535:
    return "A3F7B2E9D1C4"  # Hex string for binary
elif is_thai_column:
    return "สมชาย"         # Thai Unicode
else:
    return "John"          # ASCII text
    ↓
_build_insert_sql(columns=metadata)
    ↓
Detect binary (DUAL METHOD):
  Method 1: "FOR BIT DATA" in col_type
  Method 2: column.get("is_binary")
    ↓
if is_binary_col:
    return f"X'{hex_val}'"  # Binary literal
else:
    return f"'{value}'"     # String literal
```

---

## Troubleshooting

### **Error: [SQL0104] Token ) was not valid**

**Causes:**
1. Wrong table name (e.g., `TEST_THAI` instead of `THAI_TEST`)
2. Special characters in generated data causing SQL syntax errors
3. CCSID mismatch (UTF-8 data in EBCDIC column)

**Solutions:**
```bash
# 1. Verify table name
sudo -E bash qadmcli.sh sql execute -q "
  SELECT TABLE_NAME FROM QSYS2.SYSTABLES 
  WHERE TABLE_SCHEMA='GSLIBTST' AND TABLE_NAME LIKE '%THAI%'
" --format table

# 2. Check actual CCSID values
sudo -E bash qadmcli.sh sql execute -q "
  SELECT COLUMN_NAME, CCSID 
  FROM QSYS2.SYSCOLUMNS 
  WHERE TABLE_SCHEMA='GSLIBTST' AND TABLE_NAME='THAI_TEST'
" --format table

# 3. Run mockup with correct table name
sudo -E bash qadmcli.sh mockup generate -t THAI_TEST -l GSLIBTST -r 20
```

### **Error: Character conversion failed**

**Cause:** Attempting to insert Unicode into EBCDIC column

**Solution:** The CCSID-aware fix should prevent this. If it still occurs:
- Verify qadmcli is updated with CCSID detection code
- Check that column CCSID is correctly set in DB2

---

## Benefits

✅ **No more SQL syntax errors** from character encoding mismatches  
✅ **Automatic CCSID detection** - no manual configuration needed  
✅ **Supports mixed CCSID tables** - different columns can have different CCSIDs  
✅ **Preserves Thai language support** - CCSID 1208 and 838 columns get Thai Unicode  
✅ **Proper binary literals** - `FOR BIT DATA` columns use `X'HEXSTRING'` syntax  
✅ **Backward compatible** - works with existing tables without changes  
✅ **GlueSync ready** - binary columns replicate correctly to MSSQL VARBINARY  

---

## Future Enhancements

Potential improvements:

1. **Additional CCSID support:**
   - CCSID 284 (Spanish EBCDIC)
   - CCSID 297 (French EBCDIC)
   - CCSID 5026 (Japanese EBCDIC)

2. **Custom transliteration rules:**
   - Allow users to define custom ASCII mappings
   - Support configuration files for transliteration tables

3. **CCSID validation:**
   - Warn if table has mixed/unusual CCSIDs
   - Suggest optimal CCSID for new columns

---

## References

- [DB2 for i CCSID Documentation](https://www.ibm.com/docs/en/i/7.4?topic=information-ccsids)
- [IBM EBCDIC Code Pages](https://en.wikipedia.org/wiki/EBCDIC)
- [UTF-8 vs EBCDIC Comparison](https://www.ibm.com/docs/en/i/7.4?topic=unicode-utf-8)

---

**Last Updated:** 2026-04-30  
**Version:** qadmcli v1.x (post-CCSID fix)
