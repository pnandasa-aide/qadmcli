# QADM CLI - AS400 DB2 for i Database Management Tool

A Python-based CLI tool for managing AS400 DB2 for i database tables with connection management, table creation, journaling control, and journal entry retrieval/decoding capabilities.

## Features

- **Connection Management**: Connect to AS400 via jt400 JDBC driver with SSL support
- **Table Operations**: Create, check, and manage tables using YAML or SQL schema definitions
- **Journal Management**: Enable/disable journaling, retrieve and decode journal entries
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

Check if table exists:
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

List tables in a library:
```bash
qadmcli table list -l MYLIB
qadmcli table list -l MYLIB --json
```

### Journal Commands

Check journal status:
```bash
qadmcli journal check -n CUSTOMERS -l MYLIB
```

Enable journaling:
```bash
qadmcli journal enable -n CUSTOMERS -l MYLIB
qadmcli journal enable -n CUSTOMERS -l MYLIB --journal-library MYLIB --journal-name QSQJRN
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
qadmcli journal info -n CUSTOMERS -l MYLIB
qadmcli journal info -n CUSTOMERS -l MYLIB --json
```

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
| `connection test` | Test AS400 connection |
| `table check` | Check if table exists |
| `table create` | Create table from schema |
| `table drop-create` | Drop and recreate table |
| `table list` | List tables in library |
| `journal check` | Check journal status |
| `journal enable` | Enable journaling |
| `journal entries` | Get journal entries |
| `journal info` | Get detailed journal info |

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
│   │   └── journal.py    # Journal operations
│   ├── models/           # Data models
│   │   ├── connection.py
│   │   ├── table.py
│   │   └── journal.py
│   └── utils/            # Utilities
│       ├── logger.py
│       └── formatters.py
├── config/               # Configuration files
│   ├── connection.yaml.example
│   └── tables/           # Table schema examples
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
