#!/bin/bash
# Script to insert mockup data into THAI_TEST table
# Usage: ./insert_thai_test.sh [LIBRARY_NAME]
#        ./insert_thai_test.sh GSLIBTST "ทดสอบ" "name2" "name3" [CREATED_AT]

# To Test
# sudo -E bash qadmcli.sh sql query -q "SELECT * FROM GSLIBTST.THAI_TEST ORDER BY CREATED_AT DESC FETCH FIRST 10 ROWS ONLY"
# ./insert_thai_test.sh GSLIBTST "ทดสอบ" "name" "ทดสอบ name" now

LIBRARY=${1:-"GSLIBTST"}
TABLE="THAI_TEST"

# Custom values (optional)
CUSTOM_FIRSTNAME=${2:-""}
CUSTOM_LASTNAME=${3:-""}
CUSTOM_FULLNAME=${4:-""}
CUSTOM_CREATED_AT=${5:-""}  # "now" or specific datetime

echo "========================================="
echo "THAI_TEST Mockup Data Insertion Script"
echo "========================================="
if [ -n "$CUSTOM_FIRSTNAME" ]; then
    echo "🎯 Custom mode - using specified Thai values"
else
    echo "🎲 Random mode - generating random Thai values"
fi
if [ -n "$CUSTOM_CREATED_AT" ]; then
    echo "📅 Custom CREATED_AT: $CUSTOM_CREATED_AT"
else
    echo "📅 CREATED_AT: CURRENT TIMESTAMP (auto)"
fi
echo ""

# Step 1: Query for the next ID
echo "📊 Querying for next available ID..."

# Try to get MAX(ID), but use a fallback strategy
NEXT_ID=$(python3 << 'PYTHON_SCRIPT'
import subprocess
import json
import sys

try:
    # Try to query the database
    result = subprocess.run(
        ['sudo', '-E', 'bash', 'qadmcli.sh', 'sql', 'query', '-t', 'as400', 
         '-q', 'SELECT COALESCE(MAX(ID), 0) + 1 AS NEXT_ID FROM GSLIBTST.THAI_TEST',
         '--format', 'json'],
        capture_output=True,
        text=True,
        timeout=30
    )
    
    # Parse output to find JSON
    output = result.stdout + result.stderr
    start = output.find('[')
    end = output.rfind(']') + 1
    
    if start >= 0 and end > start:
        json_str = output[start:end]
        data = json.loads(json_str)
        if data and len(data) > 0:
            next_id = int(data[0].get('NEXT_ID', 1))
            # Add some buffer to avoid conflicts
            print(next_id + 100)
        else:
            print(10001)
    else:
        print(10002)
except Exception as e:
    # Fallback: use a timestamp-based ID
    import time
    print(int(time.time()) % 100000 + 10000)
PYTHON_SCRIPT
)

if [ -z "$NEXT_ID" ]; then
    NEXT_ID=$((RANDOM % 90000 + 10000))
    echo "⚠️  Could not query database, using random ID: $NEXT_ID"
else
    echo "✅ Using ID: $NEXT_ID"
fi
echo ""

# Step 2: Generate mockup data using Python
echo "🎲 Generating mockup data..."

# Generate all mockup data using Python and save to temp file
PYTHON_OUTPUT=$(python3 << PYTHON_SCRIPT
import random
import binascii

# Use custom values if provided, otherwise generate random
firstname = "${CUSTOM_FIRSTNAME}" if "${CUSTOM_FIRSTNAME}" else None
lastname = "${CUSTOM_LASTNAME}" if "${CUSTOM_LASTNAME}" else None
fullname = "${CUSTOM_FULLNAME}" if "${CUSTOM_FULLNAME}" else None

if not firstname:
    # Thai first names
    thai_first_names = [
        "สมชาย", "สมหญิง", "ประเสริฐ", "วิชัย", "นภาพร",
        "กิตติ", "พรรณี", "สุรชัย", "อรุณี", "ธนพล",
        "พิมพ์ใจ", "อำนาจ", "รัตนา", "วีระ", "จันทร์"
    ]
    firstname = random.choice(thai_first_names)

if not lastname:
    # Thai last names
    thai_last_names = [
        "สุขใจ", "ดีใจ", "มีชัย", "เจริญศรี", "วงศ์สว่าง",
        "ทองดี", "แก้วใส", "ศรีสุข", "พรหมมา", "รัตนกุล"
    ]
    lastname = random.choice(thai_last_names)

if not fullname:
    fullname = f"{firstname} {lastname}"

# Generate random store ID (10 chars, ASCII for CCSID 65535 binary)
store_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=10))

# Generate random store ID EBCDIC (10 chars, ASCII for CCSID 37)
store_id_ebcdic = f"STORE{random.randint(10000, 99999):05d}"

# Generate random binary data (16 bytes for CCSID 65535)
random_bytes = bytes([random.randint(0, 255) for _ in range(16)])
raw_data = binascii.hexlify(random_bytes).decode('ascii').upper()

# Output as pipe-separated to handle spaces in Thai names
print(f"{firstname}|{lastname}|{store_id}|{store_id_ebcdic}|{raw_data}|{fullname}")
PYTHON_SCRIPT
)

# Parse the pipe-separated output
IFS='|' read -r FIRSTNAME_TH LASTNAME_TH STORE_ID STORE_ID_EBCDIC RAW_DATA FULLNAME_TH <<< "$PYTHON_OUTPUT"

echo "   First Name: $FIRSTNAME_TH"
echo "   Last Name: $LASTNAME_TH"
echo "   Store ID (Binary): $STORE_ID"
echo "   Store ID (EBCDIC): $STORE_ID_EBCDIC"
echo "   Raw Data (Binary): 0x${RAW_DATA}"
echo "   Full Name: $FULLNAME_TH"
echo ""

# Step 3: Generate INSERT statement
echo "📝 Generated INSERT statement:"
echo "-----------------------------------------"

# Build INSERT based on whether CREATED_AT is specified
if [ -n "$CUSTOM_CREATED_AT" ]; then
    # Format CREATED_AT value
    if [ "$CUSTOM_CREATED_AT" = "now" ] || [ "$CUSTOM_CREATED_AT" = "NOW" ]; then
        # Use CURRENT_TIMESTAMP for "now"
        CREATED_AT_VALUE="CURRENT TIMESTAMP"
        INSERT_SQL="INSERT INTO ${LIBRARY}.${TABLE} (ID, FIRSTNAME_TH, LASTNAME_TH, STORE_ID, STORE_ID_EBCDIC, RAW_DATA, FULLNAME_TH, CREATED_AT) VALUES (${NEXT_ID}, '${FIRSTNAME_TH}', '${LASTNAME_TH}', '${STORE_ID}', '${STORE_ID_EBCDIC}', X'${RAW_DATA}', '${FULLNAME_TH}', ${CREATED_AT_VALUE})"
    else
        # Use specific datetime value (format: YYYY-MM-DD HH:MM:SS)
        CREATED_AT_VALUE="'$CUSTOM_CREATED_AT'"
        INSERT_SQL="INSERT INTO ${LIBRARY}.${TABLE} (ID, FIRSTNAME_TH, LASTNAME_TH, STORE_ID, STORE_ID_EBCDIC, RAW_DATA, FULLNAME_TH, CREATED_AT) VALUES (${NEXT_ID}, '${FIRSTNAME_TH}', '${LASTNAME_TH}', '${STORE_ID}', '${STORE_ID_EBCDIC}', X'${RAW_DATA}', '${FULLNAME_TH}', ${CREATED_AT_VALUE})"
    fi
else
    # Don't include CREATED_AT column - let DB2 use default or NULL
    INSERT_SQL="INSERT INTO ${LIBRARY}.${TABLE} (ID, FIRSTNAME_TH, LASTNAME_TH, STORE_ID, STORE_ID_EBCDIC, RAW_DATA, FULLNAME_TH) VALUES (${NEXT_ID}, '${FIRSTNAME_TH}', '${LASTNAME_TH}', '${STORE_ID}', '${STORE_ID_EBCDIC}', X'${RAW_DATA}', '${FULLNAME_TH}')"
fi

echo "$INSERT_SQL"
echo "-----------------------------------------"
echo ""

# Step 4: Ask if user wants to execute
read -p "❓ Execute this INSERT statement? (y/n): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Executing INSERT statement..."
    echo ""
    
    # Execute the INSERT
    sudo -E bash qadmcli.sh sql execute -t as400 -q "$INSERT_SQL" 2>&1
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Successfully inserted record with ID=$NEXT_ID"
        echo ""
        
        # Verify the insertion
        echo "🔍 Verifying insertion..."
        sudo -E bash qadmcli.sh sql query -t as400 -q "SELECT ID, FIRSTNAME_TH, LASTNAME_TH, STORE_ID, HEX(RAW_DATA) as RAW_DATA_HEX, FULLNAME_TH FROM ${LIBRARY}.${TABLE} WHERE ID = ${NEXT_ID}" 2>&1
    else
        echo ""
        echo "❌ Failed to insert record"
        exit 1
    fi
else
    echo ""
    echo "⏭️  Insert cancelled. You can run this statement manually:"
    echo "$INSERT_SQL"
fi

echo ""
echo "========================================="
echo "Done!"
echo "========================================="

# Show last 5 records (ordered by CREATED_AT to show most recent first)
sudo -E bash qadmcli.sh sql query -t as400 -q "SELECT ID, FIRSTNAME_TH, LASTNAME_TH, STORE_ID, FULLNAME_TH, CREATED_AT FROM GSLIBTST.THAI_TEST ORDER BY CREATED_AT DESC FETCH FIRST 5 ROWS ONLY" 2>&1
