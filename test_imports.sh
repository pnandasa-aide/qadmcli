#!/bin/bash
# Simple test - just verify imports work (no sudo needed)

cd /home/ubuntu/_qoder/qadmcli

echo "Testing Python imports..."
echo ""

# Test 1: Check if main CLI can be imported
echo -n "1. Main CLI import ... "
if python3 -c "from src.qadmcli.cli import cli" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli import cli" 2>&1 | head -5
fi

# Test 2: Check connection commands
echo -n "2. Connection commands import ... "
if python3 -c "from src.qadmcli.cli_commands.connection_commands import connection" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.connection_commands import connection" 2>&1 | head -5
fi

# Test 3: Check mockup commands
echo -n "3. Mockup commands import ... "
if python3 -c "from src.qadmcli.cli_commands.mockup_commands import mockup" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.mockup_commands import mockup" 2>&1 | head -5
fi

# Test 4: Check journal commands
echo -n "4. Journal commands import ... "
if python3 -c "from src.qadmcli.cli_commands.journal_commands import journal" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.journal_commands import journal" 2>&1 | head -5
fi

# Test 5: Check table commands
echo -n "5. Table commands import ... "
if python3 -c "from src.qadmcli.cli_commands.table_commands import table" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.table_commands import table" 2>&1 | head -5
fi

# Test 6: Check library commands
echo -n "6. Library commands import ... "
if python3 -c "from src.qadmcli.cli_commands.library_commands import library" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.library_commands import library" 2>&1 | head -5
fi

# Test 7: Check sql commands
echo -n "7. SQL commands import ... "
if python3 -c "from src.qadmcli.cli_commands.sql_commands import sql" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.sql_commands import sql" 2>&1 | head -5
fi

# Test 8: Check mssql commands
echo -n "8. MSSQL commands import ... "
if python3 -c "from src.qadmcli.cli_commands.mssql_commands import mssql" 2>/dev/null; then
    echo "✓ PASS"
else
    echo "✗ FAIL"
    python3 -c "from src.qadmcli.cli_commands.mssql_commands import mssql" 2>&1 | head -5
fi

echo ""
echo "Import tests complete!"
