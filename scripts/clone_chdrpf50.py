#!/usr/bin/env python3
"""
clone_chdrpf50.py - Clone AS400 table CHDRPF to CHDRPF50 with 50,000 records
Runs qadmcli directly via Python without container overhead
"""

import subprocess
import sys
import os
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

def execute_query(query, description=""):
    """Execute SQL query on AS400"""
    if description:
        print(f"\n{description}")
    
    print(f"  SQL: {query[:80]}...")
    
    try:
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
        if "DROP" in query.upper() and "CHDRPF50" in query.upper():
            print("  (Table doesn't exist - this is OK)")
            return None
        sys.exit(1)

def main():
    print("=" * 60)
    print("Cloning CHDRPF → CHDRPF50 (50,000 records)")
    print("=" * 60)
    
    # Step 1: Check source table exists
    print("\n📋 Step 1: Verifying source table SYNITI.CHDRPF exists...")
    result = execute_query(
        "SELECT COUNT(*) AS CNT FROM SYNITI.CHDRPF",
        ""
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
    print("\n🗑️  Step 2: Dropping CHDRPF50 if it exists...")
    execute_query(
        "DROP TABLE SYNITI.CHDRPF50",
        ""
    )
    
    # Step 3: Create table structure
    print("\n📝 Step 3: Creating CHDRPF50 with same structure...")
    execute_query(
        "CREATE TABLE SYNITI.CHDRPF50 LIKE SYNITI.CHDRPF",
        ""
    )
    
    # Step 4: Insert records
    print(f"\n📦 Step 4: Inserting 50,000 records...")
    execute_query(
        """
        INSERT INTO SYNITI.CHDRPF50 
        SELECT * FROM SYNITI.CHDRPF 
        FETCH FIRST 50000 ROWS ONLY
        """,
        ""
    )
    
    # Step 5: Verify
    print("\n✅ Step 5: Verifying clone...")
    result = execute_query(
        "SELECT COUNT(*) AS CNT FROM SYNITI.CHDRPF50",
        ""
    )
    
    if result:
        target_count = result[0][0] if isinstance(result[0], tuple) else result[0]['CNT']
        
        print(f"\n{'=' * 60}")
        print(f"📊 Clone Summary:")
        print(f"   Source (CHDRPF):    {source_count:>10,} records")
        print(f"   Target (CHDRPF50):  {target_count:>10,} records")
        print(f"   Requested:          {50000:>10,} records")
        print(f"{'=' * 60}")
        
        if target_count == 50000:
            print("✅ SUCCESS! Clone completed with exact record count.")
        elif target_count < 50000:
            print(f"⚠️  WARNING: Only {target_count:,} records copied (source has fewer than 50,000)")
        else:
            print("❌ ERROR: Unexpected record count!")
            sys.exit(1)
        
        print(f"\n🎯 Clone location: SYNITI.CHDRPF50")
    else:
        print("❌ Failed to verify clone!")
        sys.exit(1)

if __name__ == "__main__":
    main()
