#!/usr/bin/env python3
"""
clone_table.py - Clone AS400 table to any library with configurable record count

Usage:
    python3 clone_table.py
    python3 clone_table.py --source-lib SYNITI --target-lib TESTLIB --target-table CHDRPF50 --limit 50000
"""

import subprocess
import sys
import os
import argparse
import json

# Add qadmcli to Python path
QADMCLI_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))
sys.path.insert(0, QADMCLI_SRC)

# Load environment variables from .env
ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

from qadmcli.config import load_config
from qadmcli.db.connection import AS400ConnectionManager

def execute_query(query, description="", config=None):
    """Execute SQL query on AS400"""
    if description:
        print(f"\n{description}")
    
    print(f"  SQL: {query[:100]}{'...' if len(query) > 100 else ''}")
    
    try:
        if config is None:
            config = load_config(os.path.abspath(os.path.join(os.path.dirname(__file__), '../config/connection.yaml')))
        
        with AS400ConnectionManager(config) as conn:
            cursor = conn.execute(query)
            
            # Check if SELECT query
            if query.strip().upper().startswith("SELECT"):
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                cursor.close()
                
                if rows:
                    print(f"\n  Results:")
                    for row in rows[:10]:  # Show first 10 rows
                        print(f"    {dict(zip(columns, row))}")
                    if len(rows) > 10:
                        print(f"    ... and {len(rows) - 10} more rows")
                
                return rows
            else:
                # DDL/DML
                conn.commit()
                row_count = cursor.rowcount if hasattr(cursor, 'rowcount') else 0
                cursor.close()
                print(f"  ✓ Success ({row_count} rows affected)")
                return row_count
                
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        if "DROP" in query.upper():
            print("  (Table doesn't exist - this is OK)")
            return None
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Clone AS400 table to another library')
    parser.add_argument('--source-lib', default='SYNITI', help='Source library (default: SYNITI)')
    parser.add_argument('--source-table', default='CHDRPF', help='Source table name (default: CHDRPF)')
    parser.add_argument('--target-lib', default='SYNITI', help='Target library (default: SYNITI)')
    parser.add_argument('--target-table', default='CHDRPF50', help='Target table name (default: CHDRPF50)')
    parser.add_argument('--limit', type=int, default=50000, help='Max records to copy (default: 50000)')
    
    args = parser.parse_args()
    
    source_full = f"{args.source_lib}.{args.source_table}"
    target_full = f"{args.target_lib}.{args.target_table}"
    
    print("=" * 70)
    print(f"Cloning {source_full} → {target_full} ({args.limit:,} records)")
    print("=" * 70)
    
    # Load config once
    config = load_config(os.path.abspath(os.path.join(os.path.dirname(__file__), '../config/connection.yaml')))
    
    # Step 1: Check source table exists
    print(f"\n📋 Step 1: Verifying source table {source_full} exists...")
    result = execute_query(
        f"SELECT COUNT(*) AS CNT FROM {source_full}",
        "",
        config
    )
    
    if result:
        source_count = result[0][0] if isinstance(result[0], tuple) else result[0]['CNT']
        print(f"  ✓ Source table has {source_count:,} records")
        
        if source_count == 0:
            print("  ❌ Source table is empty!")
            sys.exit(1)
    else:
        print("  ❌ Cannot access source table!")
        sys.exit(1)
    
    # Step 2: Drop target table if exists
    print(f"\n🗑️  Step 2: Dropping {target_full} if it exists...")
    execute_query(
        f"DROP TABLE {target_full}",
        "",
        config
    )
    
    # Step 3: Create table structure
    print(f"\n📝 Step 3: Creating {target_full} with same structure as {source_full}...")
    execute_query(
        f"CREATE TABLE {target_full} LIKE {source_full}",
        "",
        config
    )
    
    # Step 4: Insert records
    print(f"\n📦 Step 4: Inserting {args.limit:,} records...")
    execute_query(
        f"""
        INSERT INTO {target_full} 
        SELECT * FROM {source_full} 
        FETCH FIRST {args.limit} ROWS ONLY
        """,
        "",
        config
    )
    
    # Step 5: Verify
    print(f"\n✅ Step 5: Verifying clone...")
    result = execute_query(
        f"SELECT COUNT(*) AS CNT FROM {target_full}",
        "",
        config
    )
    
    if result:
        target_count = result[0][0] if isinstance(result[0], tuple) else result[0]['CNT']
        
        print(f"\n{'=' * 70}")
        print(f"📊 Clone Summary:")
        print(f"   Source: {source_full:<40} {source_count:>10,} records")
        print(f"   Target: {target_full:<40} {target_count:>10,} records")
        print(f"   Limit:  {args.limit:>50,} records")
        print(f"{'=' * 70}")
        
        if target_count == args.limit:
            print("✅ SUCCESS! Clone completed with exact record count.")
        elif target_count < args.limit:
            print(f"⚠️  WARNING: Only {target_count:,} records copied (source has fewer than {args.limit:,})")
        else:
            print("❌ ERROR: Unexpected record count!")
            sys.exit(1)
        
        print(f"\n🎯 Clone location: {target_full}")
    else:
        print("❌ Failed to verify clone!")
        sys.exit(1)

if __name__ == "__main__":
    main()
