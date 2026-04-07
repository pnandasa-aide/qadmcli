# QADM CLI - AS400 DB2 for i Database Management Tool

A Python-based CLI tool for managing AS400 DB2 for i database tables with connection management, table creation, journaling control, and journal entry retrieval/decoding capabilities.

## Features

- **Connection Management**: Connect to AS400 via jt400 JDBC driver with SSL support
- **Table Operations**: Create, check, list, drop, empty, and reverse-engineer tables using YAML or SQL schema definitions
- **User Management**: Check, create, delete users and manage permissions
- **Journal Management**: Enable/disable journaling, retrieve and decode journal entries
- **Mockup Data Generation**: Generate realistic test data with intelligent field pattern recognition (names, emails, phones, Thai names, etc.)
- **Dual Name Display**: Shows both system names (short) and SQL names (long) for tables
- **Flexible Configuration**: Environment variable substitution, YAML-based configs
- **Rich Output**: Beautiful terminal output with tables, JSON support, and colored logging
- **Container Ready**: Podman/Docker support for portable deployment

## Prerequisites

- Python 3.11+
- Java Runtime Environment (JRE) 8+ (for jt400 JDBC driver)
- jt400.jar (IBM Toolbox for Java)
- Access to an AS400 system with DB2 for i

## Installation

### Local Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd qadmcli
```

2. Download jt400.jar:
```bash
mkdir -p lib
curl -L -o lib/jt400.jar "https://sourceforge.net/projects/jt400/files/latest/download"
```

3. Install in editable mode:
```bash
pip install -e .
```

### Container Installation (Recommended)

Using Podman (preferred for rootless security):
```bash
# Build the image
podman build -t qadmcli -f Containerfile .

# Or use podman-compose
podman-compose up -d
```

## Configuration

### 1. Connection Configuration

Copy the example configuration:
```bash
cp config/connection.yaml.example config/connection.yaml
```

Edit `config/connection.yaml`:
```yaml
as400:
  host: "as400.company.com"
  user: "${AS400_USER}"        # Uses environment variable
  password: "${AS400_PASSWORD}" # Uses environment variable
  port: 8471
  ssl: true
  database: "*LOCAL"

defaults:
  library: "QGPL"
  journal_library: "QSYS2"

logging:
  level: "INFO"
```

### 2. Environment Variables

Set credentials via environment variables:
```bash
export AS400_USER="your_username"
export AS400_PASSWORD="your_password"
export JT400_JAR="/path/to/jt400.jar"
```

Or use a `.env` file:
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Table Schema Configuration

Create table definitions in YAML or SQL format:

**YAML Format** (`config/tables/mytable.yaml`):
```yaml
table:
  name: "CUSTOMERS"
  library: "MYLIB"
  description: "Customer master table"

columns:
  - name: "CUST_ID"
    type: "DECIMAL"
    length: 10
    scale: 0
    nullable: false
  - name: "CUST_NAME"
    type: "VARCHAR"
    length: 100
    nullable: false

constraints:
  primary_key:
    name: "PK_CUSTOMERS"
    columns: ["CUST_ID"]

journaling:
  enabled: true
```

**SQL Format** (`config/tables/mytable.sql`):
```sql
CREATE TABLE MYLIB.CUSTOMERS (
    CUST_ID DECIMAL(10, 0) NOT NULL,
    CUST_NAME VARCHAR(100) NOT NULL,
    CONSTRAINT PK_CUSTOMERS PRIMARY KEY (CUST_ID)
);
```

## Usage

### Connection Commands

Test connection to AS400:
```bash
qadmcli connection test

# With custom config
qadmcli -c /path/to/connection.yaml connection test

# JSON output
qadmcli connection test --json
```

### Table Commands

Check if table exists (shows both system and SQL names):
```bash
qadmcli table check -n CUSTOMERS -l MYLIB
```

Create table from YAML schema:
```bash
# Dry run (preview SQL)
qadmcli table create -s config/tables/customers.yaml --dry-run

# Execute creation
qadmcli table create -s config/tables/customers.yaml
```

Create table from SQL file:
```bash
qadmcli table create -s config/tables/orders.sql
```

Drop and recreate table:
```bash
qadmcli table drop-create -n CUSTOMERS -l MYLIB -s config/tables/customers.yaml --force
```

Drop a table:
```bash
qadmcli table drop -n CUSTOMERS -l MYLIB --force
```

Empty table data (DELETE all rows):
```bash
qadmcli table empty -n CUSTOMERS -l MYLIB --force
```

Reverse engineer table to YAML schema:
```bash
qadmcli table reverse -n CUSTOMERS -l MYLIB
qadmcli table reverse -n CUSTOMERS -l MYLIB -o /app/schemas/customers.yaml
```

List tables in a library (shows both system and SQL names):
```bash
qadmcli table list -l MYLIB
qadmcli table list -l MYLIB --json
```

### Journal Commands

**Prerequisites:** Journal and journal receiver must exist before enabling journaling on tables.

#### Journal Lifecycle Management

**1. Create journal receiver:**
```bash
qadmcli journal create-receiver -n QSQJRN0001 -l MYLIB
qadmcli journal create-receiver -n QSQJRN0001 -l MYLIB --threshold 100000
```

**2. Create journal and attach to receiver:**
```bash
# Same library
qadmcli journal create -n QSQJRN -l MYLIB -r QSQJRN0001

# Cross-library (receiver in different library)
qadmcli journal create -n QSQJRN -l MYLIB -r QSQJRN0001 --receiver-library JRNLIB
```

**3. Rollover to new receiver (for large journals):**
```bash
# Auto-generate new receiver name
qadmcli journal rollover -j QSQJRN -l MYLIB

# Specify receiver name
qadmcli journal rollover -j QSQJRN -l MYLIB -r QSQJRN0002
```

**4. Monitor journal sizes:**
```bash
# Monitor all journals
qadmcli journal monitor

# Monitor specific library with custom threshold
qadmcli journal monitor -l MYLIB -t 500000
```

**5. View receiver chain:**
```bash
qadmcli journal receivers -j QSQJRN -l MYLIB
```

**6. Clean up old receivers:**
```bash
# Dry run first (recommended)
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2 --dry-run

# Execute cleanup
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2
```

#### Journal Operations

Check journal status:
```bash
qadmcli journal check -n CUSTOMERS -l MYLIB
```

Enable journaling:
```bash
# Use default journal from config
qadmcli journal enable -n CUSTOMERS -l MYLIB

# Specify journal explicitly (supports cross-library)
qadmcli journal enable -n CUSTOMERS -l MYLIB --journal-library JRNLIB --journal-name QSQJRN
```

Get journal entries:
```bash
# SQL format (default)
qadmcli journal entries -n CUSTOMERS -l MYLIB --limit 50

# JSON format
qadmcli journal entries -n CUSTOMERS -l MYLIB --limit 50 --format json
```

Get detailed journal info:
```bash
# Normal mode (shows entry range - may be slow for large journals)
qadmcli journal info -n CUSTOMERS -l MYLIB

# Fast mode (skips entry range query for better performance)
qadmcli journal info -n CUSTOMERS -l MYLIB --fast

# JSON output
qadmcli journal info -n CUSTOMERS -l MYLIB --json
```

**Example output:**
```
+------ Detailed Journal Information -------+
| Table: MYLIB.CUSTOMERS                    |
|                                           |
| Journal Status:                           |
|   Journaled: Yes                          |
|   Journal: MYLIB.JRN                      |
|   Receiver: MYLIB.JRNRCV0001              |
|   Receiver Attached: 2026-03-05 12:03:30  |
|   Receiver Detached: Still attached       |
|                                           |
| Table Entry Range:                        |
|   Oldest Sequence: 71288177               |
|   Newest Sequence: 71296431               |
|   Oldest Time: 2026-03-05 12:03:30.436000 |
|   Newest Time: 2026-03-05 12:03:30.559808 |
|   Total Entries: 8252                     |
+-------------------------------------------+
```

The entry range shows the oldest and newest journal sequences for this specific table, useful for:
- CDC replication starting points
- Determining how much change data is available
- Troubleshooting replication lag

List all journals:
```bash
qadmcli journal list
qadmcli journal list -l MYLIB
```

> **Note:** The `journal enable` command does NOT auto-create journals. You must explicitly create the journal receiver and journal first using `journal create-receiver` and `journal create` commands.

#### Journal Size Management Best Practices

**Problem:** Large journals with millions of entries cause slow queries (100+ seconds).

**Solution:** Regular receiver rollovers and cleanup

```bash
# 1. Monitor for large journals
qadmcli journal monitor -l MYLIB

# 2. Check receiver chain
qadmcli journal receivers -j QSQJRN -l MYLIB

# 3. Rollover to new receiver (old becomes ONLINE)
qadmcli journal rollover -j QSQJRN -l MYLIB

# 4. Verify the change
qadmcli journal receivers -j QSQJRN -l MYLIB

# 5. Clean up old receivers
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2 --dry-run
qadmcli journal cleanup -j QSQJRN -l MYLIB --keep 2
```

**Journal Size Categories:**
- **Small**: < 10,000 entries - Normal performance
- **Medium**: 10,000 - 1,000,000 entries - Use `--fast` flag for info
- **Large**: > 1,000,000 entries - Use `--fast` flag, consider rollover

**Receiver Status:**
- **ATTACHED**: Currently active receiver (never delete)
- **ONLINE**: Detached receiver (safe to delete after saving)
- **SAVED/PENDING**: Other states (review before deleting)

### User Commands

Check user existence and permissions:
```bash
qadmcli user check -u USER001
qadmcli user check -u USER001 -l MYLIB
qadmcli user check -u USER001 -l MYLIB -n "CUST*"
```

Check permissions for a specific table (includes journal permissions):
```bash
# Check user permissions on table and its related journal objects
qadmcli user check-table -u USER001 -t CUSTOMERS -l MYLIB

# Output shows:
# - Table permission (*FILE)
# - Journal permission (*JRN) - even if in different library
# - Journal receiver permission (*JRNRCV)
```

**Example output:**
```
+------------- Table Permission Check -------------+
| Checking permissions for USER001 on MYLIB.CUSTOMERS |
+--------------------------------------------------+

Table
 Object          | Type  | Authority
-----------------+-------+-----------
 MYLIB.CUSTOMERS | *FILE | *ALL

Journal
 Object     | Type | Authority
------------+------+-----------
 MYLIB.JRN  | *JRN | *ALL

Journal Receiver
 Object            | Type    | Authority
-------------------+---------+-----------
 MYLIB.JRNRCV0001  | *JRNRCV | *ALL

User has full permissions on table and journal objects.
```

This is especially useful for CDC and replication scenarios where you need to verify permissions on all related objects.

Create a new user:
```bash
qadmcli user create -u NEWUSER -p password123
qadmcli user create -u NEWUSER -p password123 -l MYLIB
```

Delete a user:
```bash
qadmcli user delete -u OLDUSER --force
```

Grant authority to user:
```bash
# Grant all authority
qadmcli user grant -u USER001 -g "*ALL" -l MYLIB

# Grant read-only authority
qadmcli user grant -u USER001 -g "*USE" -l MYLIB -n "CUST*"
```

Change user password:
```bash
qadmcli user password -u USER001 -p newpassword123
```

List user permissions:
```bash
qadmcli user permission -u USER001
qadmcli user permission -u USER001 -l MYLIB
```

### Mockup Data Commands

Generate mock data with automatic field pattern recognition:
```bash
# Dry run - preview SQL statements
qadmcli mockup generate -n CUSTOMERS -l MYLIB --dry-run -t 100

# Execute with default ratios (50% insert, 30% update, 20% delete)
qadmcli mockup generate -n CUSTOMERS -l MYLIB -t 1000

# Custom transaction mix
qadmcli mockup generate -n CUSTOMERS -l MYLIB -t 1000 \
  --insert-ratio 60 --update-ratio 30 --delete-ratio 10

# Large batch with custom batch size
qadmcli mockup generate -n CUSTOMERS -l MYLIB -t 5000 -b 200

# Use schema file for hints and validation
qadmcli mockup generate -n ORDERTRANX -l MYLIB -s config/schema/order.yaml --dry-run -t 100

# Skip schema validation when using schema file
qadmcli mockup generate -n ORDERTRANX -l MYLIB -s config/schema/order.yaml --skip-validation -t 100
```

**Supported Field Patterns:**
- **Names**: `FIRST_NAME`, `LAST_NAME`, `THAI_FIRST_NAME`, `THAI_LAST_NAME`
- **Contact**: `EMAIL`, `PHONE`, `MOBILE`, `MOBILE_NO`
- **Dates**: `DATE`, `CREATED_DATE`, `UPDATED_DATE`, `BIRTH_DATE`
- **Financial**: `AMOUNT`, `PRICE`, `FEE`, `TAX`, `BALANCE`
- **IDs**: `ID`, `CUST_ID`, `ORDER_ID`, `USER_ID`
- **Status**: `STATUS`, `TYPE`, `ORDER_STATUS`

**Thai Data Support:**
Columns containing `THAI`, `TH_`, or `_TH` will generate Thai names:
```sql
-- For columns like THAI_FIRST_NAME, THAI_LAST_NAME
INSERT INTO CUSTOMERS (THAI_FIRST_NAME, THAI_LAST_NAME)
VALUES ('สมชาย', 'แสงสว่าง');
```

#### Schema Hints

When field names are not meaningful or you want to override the default data format, you can add hints to column descriptions using the format `[hint:xxx]` in your table schema.

**How to Add Hints:**

In your YAML schema file, add hints to the `description` field:
```yaml
columns:
  - name: "CUST_NAME"
    type: "VARCHAR"
    length: 100
    description: "Customer full name [hint:full_name]"
  - name: "CONTACT_INFO"
    type: "VARCHAR"
    length: 50
    description: "Contact [hint:email]"
  - name: "STATUS_CODE"
    type: "CHAR"
    length: 2
    description: "Status [hint:choices:AC,IN,PE,DL]"
```

Or when reverse-engineering from an existing table, add the hint to the COLUMN_TEXT in DB2:
```sql
-- Add hint to column description
COMMENT ON COLUMN MYLIB.CUSTOMERS.STATUS_CODE IS 'Status [hint:choices:AC,IN,PE,DL]';
```

**Available Hints:**

| Hint | Description | Example Output |
|------|-------------|----------------|
| **Names** |||
| `first_name` | English first name | "John", "Jane" |
| `last_name` | English last name | "Smith", "Johnson" |
| `full_name` | Full English name | "John Smith" |
| `thai_first_name` | Thai first name | "สมชาย", "สมหญิง" |
| `thai_last_name` | Thai last name | "แสงสว่าง", "รุ่งโรจน์" |
| `thai_full_name` | Full Thai name | "สมชาย แสงสว่าง" |
| **Contact** |||
| `email` | Email address | "john@gmail.com" |
| `phone` / `mobile` | Thai mobile number | "0812345678" |
| **Dates** |||
| `date` / `datetime` / `timestamp` | Random date within last 2 years | `2024-03-15` |
| **Financial** |||
| `amount` / `price` / `fee` / `tax` / `balance` | Monetary amount | 1234.56 |
| **IDs** |||
| `id` | Numeric ID | 123456789 |
| `uuid` | UUID string | "550e8400-e29b-41d4-a716-446655440000" |
| **Status/Type** |||
| `status` / `type` / `code` | Single status code | "A", "I", "P", "D" |
| **Address** |||
| `address` | Street address | "123 Main St" |
| `city` | City name | "Bangkok", "New York" |
| `country` | Country code | "TH", "US", "UK" |
| **Company** |||
| `company` | Company name | "Global Corp" |
| `department` | Department code | "IT", "Sales", "HR" |
| **Text** |||
| `text` / `description` / `notes` / `remarks` | Lorem ipsum text | "Lorem ipsum dolor" |
| **Random** |||
| `random` | Random alphanumeric | "aB3xK9mP2q" |
| `hash` | Hex hash string | "a1b2c3d4e5f6..." |
| **Advanced** |||
| `constant:<value>` | Fixed constant value | As specified |
| `range:<min>:<max>` | Numeric range | Random between min-max |
| `choices:<v1>,<v2>` | Random from list | One of the choices |
| **File-Based** |||
| `file:<path>:<column>` | Read from CSV column | Value from file |
| `paired:<path>:<cols>` | Paired columns from same row | Consistent row data |

**Hint Examples:**

```yaml
# Example schema with various hints
columns:
  # Name fields with explicit hints
  - name: "FNAME"
    type: "VARCHAR"
    length: 50
    description: "First name [hint:first_name]"

  - name: "LNAME"
    type: "VARCHAR"
    length: 50
    description: "Last name [hint:last_name]"

  # Thai name field
  - name: "NAME_TH"
    type: "VARCHAR"
    length: 100
    description: "Thai name [hint:thai_full_name]"

  # Contact info with hint (field name not descriptive)
  - name: "FIELD1"
    type: "VARCHAR"
    length: 100
    description: "Email [hint:email]"

  # Status with specific choices
  - name: "ORDER_STATUS"
    type: "CHAR"
    length: 2
    description: "Status [hint:choices:PE,CF,SH,CA,CM]"

  # Numeric range hint
  - name: "AGE"
    type: "INTEGER"
    description: "Age [hint:range:18:65]"

  # Constant value hint
  - name: "COUNTRY_CODE"
    type: "CHAR"
    length: 2
    description: "Country [hint:constant:TH]"

  # Department with choices
  - name: "DEPT"
    type: "VARCHAR"
    length: 20
    description: "Department [hint:choices:IT,Sales,Marketing,HR,Finance]"
```

**Priority:**
Hints override automatic field name pattern detection. If a hint is present, it will be used regardless of the column name.

#### Schema Validation

When using `--schema` with mockup generation, the tool validates that the actual table structure matches the schema file:

```bash
# Validate schema before generating data
qadmcli mockup generate -n ORDERTRANX -l MYLIB -s config/schema/order.yaml --dry-run -t 100

# Skip validation if needed
qadmcli mockup generate -n ORDERTRANX -l MYLIB -s config/schema/order.yaml --skip-validation -t 100
```

**Validation Checks:**
- Column existence
- Data type compatibility (e.g., VARCHAR vs CHAR)
- Length and scale
- Nullable constraints

**Error Example:**
```
Schema validation failed:
  - Column 'FUND_NAME_EN' nullable mismatch: expected True, got False
  - Column 'CREATED_DATE' type mismatch: expected TIMESTAMP, got TIMESTMP
```

#### File-Based Data Generation

For realistic test data, you can use external CSV files with the `file:` or `paired:` hints:

**Single Column from File:**
```yaml
columns:
  - name: "FUND_CODE"
    type: "CHAR"
    length: 10
    description: "Fund code [hint:file:/app/config/data/funds.csv:FUND_CODE]"
```

**Paired Columns (Consistent Row Selection):**
```yaml
columns:
  - name: "FUND_CODE"
    type: "CHAR"
    length: 10
    description: "Fund code [hint:paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH,FUND_NAME_EN]"

  - name: "FUND_NAME_TH"
    type: "VARCHAR"
    length: 200
    description: "Thai fund name [hint:paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH,FUND_NAME_EN]"

  - name: "FUND_NAME_EN"
    type: "VARCHAR"
    length: 100
    description: "English fund name [hint:paired:/app/config/data/funds.csv:FUND_CODE,FUND_NAME_TH,FUND_NAME_EN]"
```

**CSV File Format:**
```csv
FUND_CODE,FUND_NAME_TH,FUND_NAME_EN
SCBSET50,กองทุนเปิดไทยพาณิชย์หุ้นบัวหลวง SET50,SCB Bualuang SET50 Fund
KTAGRO,กองทุนเปิดกรุงไทยหุ้นเกษตร,KT Agri Equity Fund
TMBGOLD,กองทุนเปิดทีเอ็มบี โกลด์,TMB Gold Fund
```

**Benefits of Paired Hints:**
- All columns with the same `paired:` hint get values from the **same row**
- Ensures data consistency (e.g., fund code matches fund name)
- Perfect for master data like products, customers, or funds

### Global Options

```bash
# Verbose output
qadmcli -v connection test

# JSON output
qadmcli --json table check -n CUSTOMERS -l MYLIB

# Custom config file
qadmcli -c /custom/path/connection.yaml table list -l MYLIB
```

## Development Workflow with Podman

### Why Podman over Docker?

- **Rootless containers**: Better security, runs without root privileges
- **Daemonless architecture**: No background service required
- **Native systemd integration**: Better Linux integration
- **Docker-compatible CLI**: Same commands work

### Setup Steps

1. **Install Podman**:
   - **Linux**: `sudo apt install podman podman-compose` (Ubuntu/Debian)
   - **Windows**: Install [Podman Desktop](https://podman-desktop.io/)
   - **macOS**: `brew install podman podman-compose`

2. **Start Podman machine** (macOS/Windows):
   ```bash
   podman machine init
   podman machine start
   ```

3. **Build and run**:
   ```bash
   # Build image
   podman build -t qadmcli -f Containerfile .
   
   # Run interactive container
   podman run -it --rm \
     -e AS400_USER=$AS400_USER \
     -e AS400_PASSWORD=$AS400_PASSWORD \
     -v $(pwd)/config:/app/config:Z \
     qadmcli connection test
   
   # Or use podman-compose
   podman-compose up -d
   podman exec -it qadmcli-dev qadmcli connection test
   ```

4. **Development with hot-reload**:
   ```bash
   podman-compose up -d
   # Edit source files locally, changes reflect immediately
   podman exec -it qadmcli-dev qadmcli table list -l MYLIB
   ```

### Volume Mounts Explained

- `:Z` suffix: Required for rootless Podman to handle SELinux labeling
- `./src:/app/src`: Mount source code for development
- `./config:/app/config`: Mount configuration files

## CLI Command Reference

| Command | Description |
|---------|-------------|
| **Connection** | |
| `connection test` | Test AS400 connection |
| **Table** | |
| `table check` | Check if table exists (shows system & SQL names) |
| `table create` | Create table from schema |
| `table drop-create` | Drop and recreate table |
| `table drop` | Drop a table |
| `table empty` | Delete all data from table |
| `table reverse` | Generate YAML schema from existing table |
| `table list` | List tables in library (shows system & SQL names) |
| **Journal** | |
| `journal check` | Check journal status |
| `journal cleanup` | Clean up old journal receivers |
| `journal create` | Create a journal |
| `journal create-receiver` | Create a journal receiver |
| `journal enable` | Enable journaling for a table |
| `journal entries` | Get journal entries |
| `journal info` | Get detailed journal info |
| `journal list` | List all journals with sizes |
| `journal monitor` | Monitor journal sizes and alert |
| `journal receivers` | Show receiver chain |
| `journal rollover` | Rollover to new receiver |
| **SQL** | |
| `sql execute` | Execute SQL queries |
| **User** | |
| `user check` | Check user existence and permissions |
| `user check-table` | Check permissions on table + journal + receiver |
| `user create` | Create a new user |
| `user delete` | Delete a user |
| `user grant` | Grant authority to user |
| `user password` | Change user password |
| `user permission` | List user permissions |
| **Mockup** | |
| `mockup generate` | Generate mock data with INSERT/UPDATE/DELETE |
| `mockup generate -s <schema>` | Generate with schema hints and validation |
| `mockup generate --skip-validation` | Skip schema validation |
| **Cross-Database** | |
| `table convert` | Convert schema between DB2 and MSSQL |
| `table create-mssql` | Create table on MSSQL from schema |
| `table compare-schemas` | Compare schemas between DB2 and MSSQL |

## Cross-Database Schema Support

qadmcli supports creating tables on both DB2 for i (AS400) and MSSQL from the same schema file, with automatic type conversion.

### Type Mappings

| DB2 for i Type | MSSQL Type | Notes |
|---------------|-----------|-------|
| `DECIMAL(p,0)` + identity | `BIGINT IDENTITY` | Auto-increment PK |
| `DECIMAL(p,s)` | `DECIMAL(p,s)` | Exact match |
| `INTEGER` | `INT` | Direct mapping |
| `VARCHAR(n)` | `VARCHAR(n)` | Direct mapping |
| `NVARCHAR(n)` | `NVARCHAR(n)` | Unicode support |
| `TIMESTAMP` | `DATETIME2` | Higher precision |
| `DATE` | `DATE` | Direct mapping |
| `CLOB` | `VARCHAR(MAX)` | Large text |

### Converting Schema

```bash
# Convert DB2 schema to MSSQL format
qadmcli table convert -s config/schema/subscriber.yaml \
  --source-db DB2 --target-db MSSQL \
  -o config/schema/subscriber_mssql.yaml

# Preview conversion
qadmcli table convert -s config/schema/subscriber.yaml \
  --source-db DB2 --target-db MSSQL
```

### Creating Tables on MSSQL

```bash
# Create table on MSSQL from DB2 schema
qadmcli table create-mssql -n subscribers \
  -s config/schema/subscriber.yaml \
  -d mydatabase --schema-name dbo

# Dry run to preview SQL
qadmcli table create-mssql -n subscribers \
  -s config/schema/subscriber.yaml \
  -d mydatabase --dry-run

# Drop and recreate
qadmcli table create-mssql -n subscribers \
  -s config/schema/subscriber.yaml \
  -d mydatabase --drop-if-exists
```

### Comparing Schemas

```bash
# Compare DB2 table with MSSQL table
qadmcli table compare-schemas \
  --db2-table GSLIBTST.SUBSCRIBER \
  --mssql-table dbo.subscribers
```

### Testing Schema Roundtrip

```bash
# 1. Create table on DB2 from schema
qadmcli table create -n SUBSCRIBER -l TESTLIB \
  -s config/schema/subscriber.yaml

# 2. Reverse engineer the table back to YAML
qadmcli table reverse -n SUBSCRIBER -l TESTLIB \
  -o reversed_subscriber.yaml

# 3. Compare original with reversed
diff config/schema/subscriber.yaml reversed_subscriber.yaml

# 4. Create on MSSQL from same schema
qadmcli table create-mssql -n subscribers \
  -s config/schema/subscriber.yaml -d targetdb
```

## Journal Entry Types

| Code | Meaning | SQL Operation |
|------|---------|---------------|
| PT | Put | INSERT |
| UP | Update | UPDATE |
| DL | Delete | DELETE |
| BR | Before Image | - |
| UR | After Image | - |

## Troubleshooting

### Connection Issues

**"Connection refused"**:
- Verify AS400 hostname/IP
- Check DRDA port (8471) is open
- Confirm AS400 is online

**"Authentication failed"**:
- Verify username/password
- Check user profile is enabled
- Confirm user has *IOSYSCFG authority if needed

**"jt400.jar not found"**:
- Download from https://sourceforge.net/projects/jt400/
- Set `JT400_JAR` environment variable
- Place in `lib/jt400.jar`

### SSL Issues

If SSL connection fails:
```yaml
as400:
  ssl: false  # Use only in development/trusted networks
```

### Journal Issues

**"Journal does not exist"**:
- Create journal first: `CRTJRN JRN(MYLIB/QSQJRN)`
- Or use existing journal library

## Project Structure

```
qadmcli/
├── src/qadmcli/           # Main source code
│   ├── cli.py            # CLI entry point
│   ├── config.py         # Configuration loader
│   ├── db/               # Database modules
│   │   ├── connection.py # AS400 connection
│   │   ├── schema.py     # Table operations
│   │   ├── journal.py    # Journal operations
│   │   ├── user.py       # User management
│   │   └── mockup.py     # Mockup data generation
│   ├── models/           # Data models
│   │   ├── connection.py
│   │   ├── table.py
│   │   └── journal.py
│   └── utils/            # Utilities
│       ├── logger.py
│       ├── formatters.py
│       └── data_generator.py  # Mockup data patterns
├── config/               # Configuration files
│   ├── connection.yaml.example
│   ├── schema/           # Table schema examples
│   └── data/             # Sample data files for mockup (CSV)
├── schemas/              # Mountable schema folder for container
├── tests/                # Test suite
├── Containerfile         # Container build
├── podman-compose.yaml   # Podman compose config
└── pyproject.toml        # Python project config
```

## License

MIT License

## Contributing

Contributions welcome! Please follow the existing code style and add tests for new features.

## Support

For issues and questions:
- GitHub Issues: https://github.com/qoder/qadmcli/issues
- Documentation: See examples in `config/tables/`
