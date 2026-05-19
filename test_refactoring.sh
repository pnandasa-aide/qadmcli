#!/bin/bash
# Test script for CLI refactoring - verifies all extracted modules work correctly

set -e

QADMCLI="./qadmcli.sh"
PASS=0
FAIL=0

echo "========================================"
echo "CLI REFACTORING - COMMAND TESTS"
echo "========================================"
echo ""

# Helper function to run tests
run_test() {
    local description="$1"
    local command="$2"
    
    echo -n "Testing: $description ... "
    
    if eval "$command" > /dev/null 2>&1; then
        echo "✓ PASS"
        PASS=$((PASS + 1))
    else
        echo "✗ FAIL"
        FAIL=$((FAIL + 1))
        echo "  Command: $command"
    fi
}

echo "1. CONNECTION COMMANDS"
echo "---------------------"
run_test "connection --help" "$QADMCLI connection --help"
run_test "connection test-as400 --help" "$QADMCLI connection test-as400 --help"
run_test "connection test-mssql --help" "$QADMCLI connection test-mssql --help"
echo ""

echo "2. MOCKUP COMMANDS"
echo "------------------"
run_test "mockup --help" "$QADMCLI mockup --help"
run_test "mockup generate --help" "$QADMCLI mockup generate --help"
run_test "mockup hint" "$QADMCLI mockup hint"
echo ""

echo "3. JOURNAL COMMANDS"
echo "-------------------"
run_test "journal --help" "$QADMCLI journal --help"
run_test "journal check --help" "$QADMCLI journal check --help"
run_test "journal list --help" "$QADMCLI journal list --help"
run_test "journal entries --help" "$QADMCLI journal entries --help"
run_test "journal info --help" "$QADMCLI journal info --help"
run_test "journal receivers --help" "$QADMCLI journal receivers --help"
run_test "journal monitor --help" "$QADMCLI journal monitor --help"
run_test "journal create --help" "$QADMCLI journal create --help"
echo ""

echo "4. TABLE COMMANDS"
echo "-----------------"
run_test "table --help" "$QADMCLI table --help"
run_test "table check --help" "$QADMCLI table check --help"
run_test "table create --help" "$QADMCLI table create --help"
run_test "table list --help" "$QADMCLI table list --help"
run_test "table drop --help" "$QADMCLI table drop --help"
run_test "table reverse --help" "$QADMCLI table reverse --help"
run_test "table convert --help" "$QADMCLI table convert --help"
run_test "table compare-schemas --help" "$QADMCLI table compare-schemas --help"
echo ""

echo "5. MAIN CLI"
echo "-----------"
run_test "qadmcli --help" "$QADMCLI --help"
run_test "qadmcli --version" "$QADMCLI --version"
echo ""

echo "========================================"
echo "TEST RESULTS"
echo "========================================"
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Total:  $((PASS + FAIL))"
echo ""

if [ $FAIL -eq 0 ]; then
    echo "✓ ALL TESTS PASSED!"
    exit 0
else
    echo "✗ SOME TESTS FAILED"
    exit 1
fi
