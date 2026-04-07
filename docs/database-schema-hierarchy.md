# Database Schema Hierarchy Comparison

This document explains how database hierarchy concepts (server, instance, database, schema, tables) differ across major database platforms.

## Quick Comparison Table

| Database | Server | Instance | Database | Schema | Table |
|----------|--------|----------|----------|--------|-------|
| **IBM DB2 for i (AS400)** | System | - | Library | - | File/Table |
| **IBM DB2 LUW** | Server | Instance | Database | Schema | Table |
| **Microsoft SQL Server** | Server | Instance | Database | Schema | Table |
| **Oracle** | Server | Instance | Database | Schema | Table |
| **MySQL** | Server | Instance | Database | - | Table |
| **PostgreSQL** | Server | Instance | Database | Schema | Table |

---

## IBM DB2 for i (AS400)

```
System (AS400) → Library → Table
     │              │
     │           (no schema level)
     │
   EZPIPE.TB_02  ← Library.Table notation
```

- **Library** = Database + Schema combined
- No separate schema concept
- Tables are addressed as `LIBRARY.TABLE`

**Example:**
```sql
SELECT * FROM EZPIPE.TB_02
```

---

## IBM DB2 LUW (Linux/Unix/Windows)

```
Server → Instance → Database → Schema → Table
                              │
                           Default: username
```

- Schema is separate from database
- Default schema = user's login name
- Can have multiple schemas per database

**Example:**
```sql
-- Connect to database
CONNECT TO sample;

-- Query with schema
SELECT * FROM db2admin.employees
```

---

## Microsoft SQL Server

```
Server → Instance → Database → Schema → Table
   │        │           │         │
   │        │        idvifd     dbo (default)
   │        │
   │     MSSQLSERVER (default)
   │
cdbsrv1\INSTANCE
```

- **Instance**: Can run multiple SQL Server instances on one server
- **Database**: Like `idvifd`, `master`, `tempdb`
- **Schema**: Namespace within database (default: `dbo`)
- Full path: `server.database.schema.table`

**Example:**
```sql
-- Fully qualified name
SELECT * FROM cdbsrv1.idvifd.dbo.tlifelicns

-- With default database
SELECT * FROM dbo.tlifelicns
```

---

## Oracle

```
Server → Instance (SID) → Database → Schema → Table
                                    │
                              User = Schema
```

- **Instance**: Identified by SID (System Identifier)
- **Schema** = User account
- Each user has their own schema by default
- `SCOTT.EMP` = Schema.Table

**Example:**
```sql
-- Connect as user SCOTT
sqlplus scott/tiger@ORCL

-- Query own schema
SELECT * FROM emp

-- Query other schema
SELECT * FROM hr.employees
```

---

## MySQL / MariaDB

```
Server → Instance → Database → Table
                       │
                    (schema = database)
```

- **Database = Schema** (synonymous)
- No separate schema level
- `database.table` notation

**Example:**
```sql
-- Use database
USE mydb;

-- Query table
SELECT * FROM users

-- Or with database prefix
SELECT * FROM mydb.users
```

---

## PostgreSQL

```
Server → Cluster → Database → Schema → Table
                              │
                           public (default)
```

- **Cluster**: Collection of databases sharing config
- **Schema**: Namespace within database (default: `public`)
- Supports multiple schemas per database

**Example:**
```sql
-- Connect to database
\c mydb

-- Query with schema
SELECT * FROM public.users

-- Or custom schema
SELECT * FROM sales.orders
```

---

## Syniti Metadata Mapping Example

| Syniti Element | DB2 (Source) | MSSQL (Target) |
|----------------|--------------|----------------|
| **Connection** | DB2 Server | cdbsrv1 |
| **Catalog** | - | idvifd (database) |
| **Schema** | CL5DTA, TCADTA, etc. | dbo |
| **Table** | AGLFPF, TAGCPF | tlifelicns, tfdaglfpf |

**Why only 1 schema in MSSQL?**
- Syniti's target uses a single `dbo` schema
- All 387 tables are in `dbo` schema within `idvifd` database
- This is common for migration targets - flatten to single schema

---

## Connection String Examples

| Database | Connection String |
|----------|-------------------|
| **DB2 for i** | `jdbc:as400://server/library` |
| **DB2 LUW** | `jdbc:db2://server:50000/database:currentSchema=SCHEMA` |
| **MSSQL** | `jdbc:sqlserver://server:1433;databaseName=idvifd` |
| **Oracle** | `jdbc:oracle:thin:@server:1521:SID` |
| **MySQL** | `jdbc:mysql://server:3306/database` |
| **PostgreSQL** | `jdbc:postgresql://server:5432/database?currentSchema=public` |

---

## Summary Table

| Concept | DB2 i | MSSQL | Oracle | MySQL | PostgreSQL |
|---------|-------|-------|--------|-------|------------|
| **Schema separate?** | ❌ No | ✅ Yes | ✅ Yes (User) | ❌ No | ✅ Yes |
| **Multi-schema per DB?** | N/A | ✅ Yes | ✅ Yes | N/A | ✅ Yes |
| **Default schema** | Library name | `dbo` | Username | Database name | `public` |
| **Table reference** | `LIB.TABLE` | `DB.SCHEMA.TABLE` | `SCHEMA.TABLE` | `DB.TABLE` | `SCHEMA.TABLE` |

---

## Notes for qadmcli

- **DB2 for i**: Use library name as schema parameter
- **MSSQL**: Always specify database and schema (default: `dbo`)
- The converter handles schema naming automatically based on source type
