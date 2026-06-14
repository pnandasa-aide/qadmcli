#!/bin/bash
# clone_table.sh - Clone AS400 table with optional journal enablement
# Usage: ./clone_table.sh SOURCE_LIB.SOURCE_TABLE TARGET_LIB.TARGET_TABLE [RECORD_LIMIT]
# Example: ./clone_table.sh SYNITI.CHDRPF50 TBLIBTST.CHDRPF50 50000

# Parse arguments
source_full="$1"
target_full="$2"
record_limit="${3:-50000}"  # Default 50,000 if not specified

# Validate arguments
if [ -z "$source_full" ] || [ -z "$target_full" ]; then
    echo "Usage: $0 SOURCE_LIB.SOURCE_TABLE TARGET_LIB.TARGET_TABLE [RECORD_LIMIT]"
    echo ""
    echo "Examples:"
    echo "  $0 SYNITI.CHDRPF TBLIBTST.CHDRPF50          # Clone with 50k records"
    echo "  $0 SYNITI.CHDRPF TBLIBTST.CHDRPF50 100000   # Clone with 100k records"
    echo "  $0 GSLIBTST.CUSTOMERS TESTLIB.CUSTOMERS_BAK  # Clone different table"
    exit 1
fi

# Parse library and table names
SOURCE_LIB=$(echo "$source_full" | cut -d'.' -f1)
SOURCE_TABLE=$(echo "$source_full" | cut -d'.' -f2)
TARGET_LIB=$(echo "$target_full" | cut -d'.' -f1)
TARGET_TABLE=$(echo "$target_full" | cut -d'.' -f2)

# Validate format
if [ -z "$SOURCE_LIB" ] || [ -z "$SOURCE_TABLE" ] || [ -z "$TARGET_LIB" ] || [ -z "$TARGET_TABLE" ]; then
    echo "❌ Error: Invalid format. Use LIBRARY.TABLE format"
    echo "   Example: SYNITI.CHDRPF50"
    exit 1
fi

set -e

# Set qadmcli path
QADMCLI="$(dirname "$0")/../qadmcli.sh"

echo "========================================="
echo "AS400 Table Clone with Journal Enablement"
echo "========================================="
echo "Source:  $source_full"
echo "Target:  $target_full"
echo "Limit:   $record_limit records"
echo "========================================="

# Step 1: Verify source table exists
echo ""
echo "Step 1: Verifying source table $source_full exists..."
$QADMCLI sql execute -q "SELECT COUNT(*) AS CNT FROM $source_full" -f json

echo ""
echo "Step 2: Dropping $target_full if it exists..."
$QADMCLI sql execute -q "DROP TABLE $target_full" 2>/dev/null || echo "  (Table doesn't exist - OK)"

# Step 3: Create table with same structure
echo ""
echo "Step 3: Creating $target_full with same structure as $source_full..."
$QADMCLI sql execute -q "CREATE TABLE $target_full LIKE $source_full"

# Step 4: Copy records
echo ""
echo "Step 4: Inserting $record_limit records from $source_full to $target_full..."
$QADMCLI sql execute -q "
  INSERT INTO $target_full 
  SELECT * FROM $source_full 
  FETCH FIRST $record_limit ROWS ONLY
"

# Step 5: Verify record count
echo ""
echo "Step 5: Verifying record count..."
$QADMCLI sql execute -q "SELECT COUNT(*) AS RECORD_COUNT FROM $target_full" -f json

# Step 6: Enable journaling on target table
echo ""
echo "Step 6: Enabling journal on $target_full..."
$QADMCLI journal enable --library "$TARGET_LIB" --table "$TARGET_TABLE"

# Step 7: Verify journal status
echo ""
echo "Step 7: Verifying journal status..."
$QADMCLI journal status --library "$TARGET_LIB" --table "$TARGET_TABLE"

echo ""
echo "========================================="
echo "✅ Clone completed successfully!"
echo "========================================="
echo "Source:  $source_full"
echo "Target:  $target_full"
echo "Records: $record_limit"
echo "Journal: Enabled on $target_full"
echo "========================================="
