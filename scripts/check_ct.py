#!/usr/bin/env python3
"""Check if Change Tracking is enabled on MSSQL target database"""

import os
import pyodbc

# Load credentials
ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

MSSQL_HOST = os.getenv('MSSQL_HOST', '192.168.13.62')
MSSQL_USER = os.getenv('MSSQL_USER', 'gstgdblogin')
MSSQL_PASS = os.getenv('MSSQL_PASSWORD', '')
MSSQL_DB = os.getenv('MSSQL_DATABASE', 'GSTargetDB')

print(f"Connecting to MSSQL at {MSSQL_HOST}...")
print(f"Database: {MSSQL_DB}")

try:
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={MSSQL_HOST};"
        f"DATABASE={MSSQL_DB};"
        f"UID={MSSQL_USER};"
        f"PWD={MSSQL_PASS};"
        f"TrustServerCertificate=yes"
    )
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    
    # Check if CT is enabled for database
    print("\n=== Change Tracking Status ===")
    cursor.execute("""
        SELECT 
            d.name,
            ct.is_auto_cleanup_on,
            ct.retention_period,
            ct.retention_period_units_desc
        FROM sys.change_tracking_databases ct
        JOIN sys.databases d ON ct.database_id = d.database_id
        WHERE d.name = ?
    """, (MSSQL_DB,))
    
    row = cursor.fetchone()
    if row:
        print(f"Database: {row.name}")
        print(f"CT Enabled: YES")
        print(f"Auto Cleanup: {row.is_auto_cleanup_on}")
        print(f"Retention: {row.retention_period} {row.retention_period_units_desc}")
    else:
        print(f"CT Enabled: NO (or database not found)")
    
    # Check CT enabled tables
    print("\n=== CT Enabled Tables ===")
    cursor.execute("""
        SELECT 
            t.name as table_name,
            s.name as schema_name,
            ct.is_track_columns_updated_on
        FROM sys.change_tracking_tables ct
        JOIN sys.tables t ON ct.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
    """)
    
    tables = cursor.fetchall()
    if tables:
        for t in tables:
            print(f"  - {t.schema_name}.{t.name} (track columns: {t.is_track_columns_updated_on})")
    else:
        print("  No tables have CT enabled")
    
    # If CUSTOMERS table has CT, show sample changes
    cursor.execute("""
        SELECT OBJECT_ID FROM sys.tables t
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE t.name = 'CUSTOMERS' AND s.name = 'dbo'
    """)
    
    table_row = cursor.fetchone()
    if table_row:
        table_id = table_row[0]
        print(f"\n=== Sample CT Changes for dbo.CUSTOMERS ===")
        
        # Get recent changes using CHANGETABLE
        cursor.execute(f"""
            SELECT TOP 10
                ct.CUST_ID,
                ct.SYS_CHANGE_VERSION,
                ct.SYS_CHANGE_CREATION_VERSION,
                ct.SYS_CHANGE_OPERATION,
                ct.SYS_CHANGE_CONTEXT
            FROM CHANGETABLE(CHANGES dbo.CUSTOMERS, 0) ct
            ORDER BY ct.SYS_CHANGE_VERSION DESC
        """)
        
        changes = cursor.fetchall()
        if changes:
            print(f"Found {len(changes)} recent changes:")
            for c in changes:
                print(f"  PK={c.CUST_ID}, Ver={c.SYS_CHANGE_VERSION}, Op={c.SYS_CHANGE_OPERATION}")
        else:
            print("  No changes found (or CT not enabled for this table)")
    
    cursor.close()
    conn.close()
    print("\n✓ Done")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
