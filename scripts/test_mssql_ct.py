#!/usr/bin/env python3
"""
Test script for MSSQL Change Tracking features.
Run this after setting up CT with mssql_ct_setup.sql
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_ct_status():
    """Test CT status check."""
    print("=" * 60)
    print("Testing: qadmcli mssql ct status")
    print("=" * 60)
    
    # Simulate the command
    print("\nCommand: qadmcli mssql ct status -t INSURANCE_PRODUCTS -s dbo")
    print("\nExpected output:")
    print("  Change Tracking Status for dbo.INSURANCE_PRODUCTS")
    print("  Database: GSTargetDB")
    print("  CT Enabled on Database: Yes")
    print("  CT Enabled on Table: Yes")
    print("  Retention Period: 2 days")
    print("  Auto Cleanup: Yes")
    
    print("\nCommand: qadmcli mssql ct status -t NON_EXISTENT_TABLE -s dbo")
    print("\nExpected output:")
    print("  Change Tracking Status for dbo.NON_EXISTENT_TABLE")
    print("  Database: GSTargetDB")
    print("  CT Enabled on Database: Yes")
    print("  CT Enabled on Table: No")
    print("\n  To enable CT on table:")
    print("    ALTER TABLE [dbo].[NON_EXISTENT_TABLE] ENABLE CHANGE_TRACKING")


def test_ct_changes():
    """Test CT changes query."""
    print("\n" + "=" * 60)
    print("Testing: qadmcli mssql ct changes")
    print("=" * 60)
    
    print("\nCommand: qadmcli mssql ct changes -t INSURANCE_PRODUCTS -s dbo --since-version 0")
    print("\nExpected output:")
    print("  Current CT Version: 10, Min Valid Version: 0")
    print("  ┌─────────────────────┬──────────────────────┬──────────┬──────────┐")
    print("  │ SYS_CHANGE_VERSION  │ SYS_CHANGE_OPERATION │ PK_PROD… │ STATUS   │")
    print("  ├─────────────────────┼──────────────────────┼──────────┼──────────┤")
    print("  │ 1                   │ I                    │ 100      │ ACTIVE   │")
    print("  │ 2                   │ I                    │ 101      │ ACTIVE   │")
    print("  │ 3                   │ I                    │ 102      │ ACTIVE   │")
    print("  │ 4                   │ I                    │ 103      │ ACTIVE   │")
    print("  │ 5                   │ I                    │ 104      │ ACTIVE   │")
    print("  │ 8                   │ U                    │ 100      │ INACTIVE │")
    print("  └─────────────────────┴──────────────────────┴──────────┴──────────┘")
    print("  Operations: I=5, U=1")
    
    print("\nCommand: qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since \"2025-04-09 10:00:00\" --format json")
    print("\nExpected output:")
    print("""  [
    {
      "SYS_CHANGE_VERSION": 8,
      "SYS_CHANGE_OPERATION": "U",
      "SYS_CHANGE_COLUMNS": null,
      "SYS_CHANGE_CONTEXT": null,
      "PRIMARY_KEY_VALUES": {"PRODUCT_ID": 100}
    }
  ]""")


def test_ct_workflow():
    """Test complete CT workflow."""
    print("\n" + "=" * 60)
    print("Complete CT Workflow Example")
    print("=" * 60)
    
    workflow = """
1. Check if CT is enabled on database and table:
   $ qadmcli mssql ct status -t INSURANCE_PRODUCTS

2. Get current version (for baseline):
   $ qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 0 --limit 1
   Note the highest SYS_CHANGE_VERSION (e.g., 10)

3. Application makes changes (INSERT/UPDATE/DELETE)...

4. Query changes since baseline:
   $ qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 10

5. Process changes by operation type:
   - I (Insert): Add new records to target
   - U (Update): Update existing records in target
   - D (Delete): Remove records from target

6. Update baseline version for next sync:
   New baseline = highest SYS_CHANGE_VERSION from step 4
"""
    print(workflow)


def test_integration_with_mockup():
    """Test CT with mockup data generation."""
    print("\n" + "=" * 60)
    print("Integration with Mockup Data Generation")
    print("=" * 60)
    
    workflow = """
1. Generate mock data (triggers CT inserts):
   $ qadmcli mockup generate -t INSURANCE_PRODUCTS -l dbo -n 5

2. Query CT to see inserted records:
   $ qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 0

3. Update some records (triggers CT updates):
   $ qadmcli sql execute -q "UPDATE dbo.INSURANCE_PRODUCTS SET STATUS='INACTIVE' WHERE PRODUCT_ID > 100"

4. Query CT to see updated records:
   $ qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 0
   
   Look for SYS_CHANGE_OPERATION = 'U'

5. Delete records (triggers CT deletes):
   $ qadmcli sql execute -q "DELETE FROM dbo.INSURANCE_PRODUCTS WHERE PRODUCT_ID > 103"

6. Query CT to see all operations:
   $ qadmcli mssql ct changes -t INSURANCE_PRODUCTS --since-version 0
   
   Look for SYS_CHANGE_OPERATION = 'D'
"""
    print(workflow)


if __name__ == "__main__":
    print("MSSQL Change Tracking Test Script")
    print("=" * 60)
    print("\nThis script shows expected outputs for CT commands.")
    print("Run the actual commands after executing mssql_ct_setup.sql\n")
    
    test_ct_status()
    test_ct_changes()
    test_ct_workflow()
    test_integration_with_mockup()
    
    print("\n" + "=" * 60)
    print("All tests described!")
    print("=" * 60)
