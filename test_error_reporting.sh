#!/bin/bash
# Test enhanced error reporting

cd ~/_qoder/qadmcli

echo "Testing ALTER TABLE command with enhanced error reporting..."
echo ""

# Run the command
bash qadmcli.sh as400 execute -q "
  ALTER TABLE GSLIBTST.CUSTOMERS2 
  ADD COLUMN CREATED_AT VARCHAR(20)
"

echo ""
echo "Exit code: $?"
echo ""
echo "If you see 'Error [ExceptionType]: details', the fix is working!"
