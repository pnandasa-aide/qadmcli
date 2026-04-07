#!/usr/bin/env python3
"""Check which tables were skipped during Syniti conversion."""

import xml.etree.ElementTree as ET
from pathlib import Path

def main():
    xml_path = Path("schemas/syniti/MetaData_20230608.xml")
    output_dir = Path("schemas/converted")
    
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Get all tables from XML
    xml_tables = {}
    for table_elem in root.findall('.//DBMMTables'):
        table_id = int(table_elem.findtext('TableID', '0'))
        table_name = table_elem.findtext('Name', '').upper()
        xml_tables[table_name] = {'id': table_id, 'columns': 0}
    
    # Count fields per table
    for field_elem in root.findall('.//DBMMFields'):
        table_id = int(field_elem.findtext('TableID', '0'))
        for name, info in xml_tables.items():
            if info['id'] == table_id:
                info['columns'] += 1
                break
    
    # Get converted files
    converted_files = list(output_dir.glob('*.yaml'))
    converted_names = {f.stem.upper() for f in converted_files}
    
    # Find missing tables
    missing_tables = []
    for name, info in xml_tables.items():
        yaml_name = name.lower()
        if yaml_name not in {f.stem for f in converted_files}:
            missing_tables.append((name, info['id'], info['columns']))
    
    # Print summary
    print(f"Total tables in XML: {len(xml_tables)}")
    print(f"Converted YAML files: {len(converted_files)}")
    print(f"Missing tables: {len(missing_tables)}")
    print()
    
    # Categorize missing tables
    no_columns = [(n, tid, c) for n, tid, c in missing_tables if c == 0]
    has_columns = [(n, tid, c) for n, tid, c in missing_tables if c > 0]
    
    if no_columns:
        print(f"Tables skipped (no columns defined): {len(no_columns)}")
        for name, tid, cols in sorted(no_columns):
            print(f"  - {name} (ID: {tid})")
        print()
    
    if has_columns:
        print(f"Tables with columns but not converted: {len(has_columns)}")
        for name, tid, cols in sorted(has_columns):
            print(f"  - {name} (ID: {tid}, columns: {cols})")
        print()
    
    # Show tables with most columns
    print("Top 10 tables by column count:")
    sorted_tables = sorted(xml_tables.items(), key=lambda x: x[1]['columns'], reverse=True)
    for name, info in sorted_tables[:10]:
        status = "✓" if name.lower() in converted_names else "✗"
        print(f"  {status} {name}: {info['columns']} columns")

if __name__ == "__main__":
    main()
