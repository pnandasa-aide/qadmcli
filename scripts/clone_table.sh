#!/bin/bash
# clone_table.sh - Clone AS400 table with journal enablement (Python version)
# Usage: ./clone_table.sh SOURCE_LIB.SOURCE_TABLE TARGET_LIB.TARGET_TABLE [RECORD_LIMIT]
# Example: ./clone_table.sh SYNITI.CHDRPF50 TBLIBTST.CHDRPF50 50000

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

echo "========================================="
echo "AS400 Table Clone with Journal Enablement"
echo "========================================="
echo "Source:  $source_full"
echo "Target:  $target_full"
echo "Limit:   $record_limit records"
echo "========================================="

# Run Python script for the clone operation
python3 "${SCRIPT_DIR}/clone_table_with_journal.py" \
    --source "$source_full" \
    --target "$target_full" \
    --limit "$record_limit" \
    --target-lib "$TARGET_LIB" \
    --target-table "$TARGET_TABLE"
