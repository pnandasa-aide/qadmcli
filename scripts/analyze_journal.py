#!/usr/bin/env python3
import json
from collections import Counter

with open('/tmp/journal_output.txt', 'r') as f:
    lines = f.readlines()

json_start = None
for i, line in enumerate(lines):
    if line.strip() == '[':
        json_start = i
        break

if json_start:
    json_data = ''.join(lines[json_start:])
    entries = json.loads(json_data)
    
    print("=" * 60)
    print("AS400 JOURNAL ENTRY ANALYSIS")
    print("=" * 60)
    print(f"\nTotal entries: {len(entries)}")
    
    codes = Counter(e.get('code') for e in entries)
    print("\nAll entry codes:")
    for code, count in sorted(codes.items(), key=lambda x: x[1], reverse=True):
        print(f"  {code}: {count}")
    
    recent = [e for e in entries if e.get('entry_number', 0) > 34200]
    recent_codes = Counter(e.get('code') for e in recent)
    
    print(f"\nRecent entries (>34200): {len(recent)}")
    for code, count in sorted(recent_codes.items()):
        print(f"  {code}: {count}")
    
    pt = recent_codes.get('PT', 0)
    up = recent_codes.get('UP', 0)
    dl = recent_codes.get('DL', 0)
    
    print(f"\nDATA OPERATIONS:")
    print(f"  INSERT (PT): {pt}")
    print(f"  UPDATE (UP): {up}")
    print(f"  DELETE (DL): {dl}")
    print(f"  TOTAL: {pt + up + dl}")
