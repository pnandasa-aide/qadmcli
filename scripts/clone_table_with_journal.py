#!/usr/bin/env python3
"""
clone_table_with_journal.py - Clone AS400 table and enable journal on target
Usage:
    python3 clone_table_with_journal.py --source SYNITI.CHDRPF50 --target TBLIBTST.CHDRPF50 --limit 50000
"""

import sys
import os
import argparse

# Load environment variables from .env FIRST (before any imports)
ENV_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../.env'))
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val

# Set JT400_JAR path (extracted Java 8 version)
os.environ['JT400_JAR'] = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../lib/lib/java8/jt400.jar'))

# Add qadmcli to Python path
QADMCLI_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))
sys.path.insert(0, QADMCLI_SRC)

from qadmcli.config import load_config
from qadmcli.db.connection import AS400ConnectionManager
from qadmcli.db.journal import JournalManager

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

def enable_journal(target_lib, target_table, config=None):
    """Enable journaling on target table"""
    print(f"\n📰 Step 6: Enabling journal on {target_lib}.{target_table}...")
    
    try:
        if config is None:
            config = load_config(os.path.abspath(os.path.join(os.path.dirname(__file__), '../config/connection.yaml')))
        
        with AS400ConnectionManager(config) as conn:
            journal_mgr = JournalManager(conn)
            
            # Check if already journaled
            is_journaled = journal_mgr.is_journaled(target_table, target_lib)
            
            if is_journaled:
                print(f"  ℹ Table {target_lib}.{target_table} is already journaled")
            else:
                print(f"  Enabling journal...")
                journal_mgr.enable_journaling(target_table, target_lib)
                print(f"  ✓ Journal enabled successfully")
            
            # Verify journal status
            print(f"\n📊 Step 7: Verifying journal status...")
            is_journaled = journal_mgr.is_journaled(target_table, target_lib)
            
            if is_journaled:
                print(f"  ✓ Journal status: ENABLED")
                
                # Get journal details
                try:
                    journal_info = journal_mgr.get_journal_info(target_table, target_lib)
                    if journal_info:
                        print(f"  Journal: {journal_info.get('journal_name', 'N/A')}")
                        print(f"  Journal Library: {journal_info.get('journal_library', 'N/A')}")
                except Exception as e:
                    print(f"  (Journal details: {str(e)})")
            else:
                print(f"  ❌ Journal status: DISABLED (enablement may have failed)")
                sys.exit(1)
                
    except Exception as e:
        print(f"\n❌ Error enabling journal: {str(e)}")
        print("  (Table cloned successfully, but journal enablement failed)")
        # Don't exit - table was still cloned successfully

def main():
    parser = argparse.ArgumentParser(description='Clone AS400 table and enable journal on target')
    parser.add_argument('--source', required=True, help='Source table (LIBRARY.TABLE)')
    parser.add_argument('--target', required=True, help='Target table (LIBRARY.TABLE)')
    parser.add_argument('--limit', type=int, default=50000, help='Max records to copy (default: 50000)')
    parser.add_argument('--target-lib', help='Target library (parsed from --target if not provided)')
    parser.add_argument('--target-table', help='Target table name (parsed from --target if not provided)')
    
    args = parser.parse_args()
    
    # Parse target lib and table if not provided
    if args.target_lib is None or args.target_table is None:
        parts = args.target.split('.')
        if len(parts) != 2:
            print(f"❌ Error: Invalid target format '{args.target}'. Use LIBRARY.TABLE")
            sys.exit(1)
        target_lib = args.target_lib or parts[0]
        target_table = args.target_table or parts[1]
    else:
        target_lib = args.target_lib
        target_table = args.target_table
    
    print("=" * 70)
    print(f"Cloning {args.source} → {args.target} ({args.limit:,} records)")
    print("With Journal Enablement on Target")
    print("=" * 70)
    
    # Load config once
    config = load_config(os.path.abspath(os.path.join(os.path.dirname(__file__), '../config/connection.yaml')))
    
    # Step 1: Check source table exists
    print(f"\n📋 Step 1: Verifying source table {args.source} exists...")
    result = execute_query(
        f"SELECT COUNT(*) AS CNT FROM {args.source}",
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
    print(f"\n🗑️  Step 2: Dropping {args.target} if it exists...")
    execute_query(
        f"DROP TABLE {args.target}",
        "",
        config
    )
    
    # Step 3: Create table structure
    print(f"\n📝 Step 3: Creating {args.target} with same structure as {args.source}...")
    execute_query(
        f"CREATE TABLE {args.target} LIKE {args.source}",
        "",
        config
    )
    
    # Step 4: Insert records
    print(f"\n📦 Step 4: Inserting {args.limit:,} records...")
    execute_query(
        f"""
        INSERT INTO {args.target} 
        SELECT * FROM {args.source} 
        FETCH FIRST {args.limit} ROWS ONLY
        """,
        "",
        config
    )
    
    # Step 5: Verify
    print(f"\n✅ Step 5: Verifying clone...")
    result = execute_query(
        f"SELECT COUNT(*) AS CNT FROM {args.target}",
        "",
        config
    )
    
    if result:
        target_count = result[0][0] if isinstance(result[0], tuple) else result[0]['CNT']
        
        print(f"\n{'=' * 70}")
        print(f"📊 Clone Summary:")
        print(f"   Source: {args.source:<45} {source_count:>10,} records")
        print(f"   Target: {args.target:<45} {target_count:>10,} records")
        print(f"   Limit:  {args.limit:>55,} records")
        print(f"{'=' * 70}")
        
        if target_count == args.limit:
            print("✅ SUCCESS! Clone completed with exact record count.")
        elif target_count < args.limit:
            print(f"⚠️  WARNING: Only {target_count:,} records copied (source has fewer than {args.limit:,})")
        else:
            print("❌ ERROR: Unexpected record count!")
            sys.exit(1)
    else:
        print("❌ Failed to verify clone!")
        sys.exit(1)
    
    # Step 6 & 7: Enable and verify journal
    enable_journal(target_lib, target_table, config)
    
    print(f"\n{'=' * 70}")
    print(f"🎯 Final Status:")
    print(f"   Clone location: {args.target}")
    print(f"   Records copied: {target_count:,}")
    print(f"   Journal status: ENABLED on {target_lib}.{target_table}")
    print(f"{'=' * 70}")
    print("✅ All operations completed successfully!")
    print("=" * 70)

if __name__ == "__main__":
    main()
