#!/usr/bin/env python3
import os
import sys

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
                key, val = line.strip().split('=', 1)
                os.environ[key] = val

from qadmcli.db.connection import AS400ConnectionManager
from qadmcli.db.journal import JournalManager

config = {
    'host': '161.82.146.249',
    'user': os.getenv('AS400_USER', 'user001'),
    'password': os.getenv('AS400_PASSWORD', ''),
    'port': 8471,
    'ssl': False,
    'database': 'GSLIBTST'
}

print(f"Connecting to AS400 at {config['host']}...")
conn = AS400ConnectionManager(config)
conn.connect()
print("Connected!\n")

journal_mgr = JournalManager(conn)
table_name = "CUSTOMERS"
library = "GSLIBTST"

print(f"Checking journal status for {library}.{table_name}...")
is_journaled = journal_mgr.is_journaled(table_name, library)
print(f"  Is Journaled: {is_journaled}\n")

if is_journaled:
    print("Reading last 5 journal entries...")
    entries = journal_mgr.get_journal_entries(table_name, library, limit=5)
    print(f"  Found {len(entries)} entries:")
    for entry in entries:
        print(f"    #{entry.entry_number} | {entry.entry_type} | {entry.entry_timestamp}")

conn.disconnect()
print("\nDone!")
