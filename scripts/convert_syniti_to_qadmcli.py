#!/usr/bin/env python3
"""
Convert Syniti Metadata XML to qadmcli YAML Schema Format

Usage:
    python convert_syniti_to_qadmcli.py <input_xml> [--output-dir <dir>] [--library <name>]

Example:
    python convert_syniti_to_qadmcli.py schemas/syniti/MetaData_20230608.xml \
        --output-dir schemas/converted --library GSLIBTST
"""

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
import yaml


# Syniti to DB2 for i type mapping
SYNITI_TO_DB2_TYPE_MAP = {
    # Character types
    "CHAR": "CHAR",
    "VARCHAR": "VARCHAR",
    # Numeric types
    "DECIMAL": "DECIMAL",
    "NUMERIC": "DECIMAL",
    "INTEGER": "INTEGER",
    "INT": "INTEGER",
    "SMALLINT": "SMALLINT",
    "BIGINT": "BIGINT",
    "FLOAT": "DOUBLE",
    "REAL": "REAL",
    "DOUBLE": "DOUBLE",
    # Date/Time types
    "DATE": "DATE",
    "TIME": "TIME",
    "TIMESTAMP": "TIMESTAMP",
    "datetime": "TIMESTAMP",
    # Binary types
    "BINARY": "CHAR",  # With CCSID 65535
    "VARBINARY": "VARCHAR",  # With CCSID 65535
    "BLOB": "BLOB",
    "CLOB": "CLOB",
    "DBCLOB": "DBCLOB",
    # Other
    "GRAPHIC": "GRAPHIC",
    "VARGRAPHIC": "VARGRAPHIC",
}


def parse_syniti_xml(xml_path: str) -> dict[int, dict[str, Any]]:
    """Parse Syniti metadata XML and extract table/field information."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Extract tables
    tables = {}
    for table_elem in root.findall(".//DBMMTables"):
        table_id = int(table_elem.findtext("TableID", "0"))
        table_name = table_elem.findtext("Name", "")
        sys_name = table_elem.findtext("SysName", table_name)
        
        tables[table_id] = {
            "name": table_name.upper(),
            "sys_name": sys_name.upper() if sys_name else table_name.upper(),
            "columns": [],
            "primary_keys": [],
        }
    
    # Extract fields and associate with tables
    for field_elem in root.findall(".//DBMMFields"):
        field_id = int(field_elem.findtext("FieldID", "0"))
        table_id = int(field_elem.findtext("TableID", "0"))
        
        if table_id not in tables:
            continue
        
        field_name = field_elem.findtext("Name", "").upper()
        field_type = field_elem.findtext("Type", "").upper()
        size = int(field_elem.findtext("Size", "0"))
        precision = int(field_elem.findtext("Precision", "0"))
        scale = int(field_elem.findtext("Scale", "0"))
        ccsid = int(field_elem.findtext("Ccsid", "0"))
        allow_null = field_elem.findtext("AllowNull", "Y").upper() == "Y"
        description = field_elem.findtext("Description", "") or ""
        pk_pos = int(field_elem.findtext("PrimaryKeyPos", "0"))
        is_auto_increment = field_elem.findtext("IsAutoIncrement", "N").upper() == "Y"
        default_elem = field_elem.find("Default")
        default_value = default_elem.text if default_elem is not None else None
        
        # Map type to DB2 for i
        db2_type = SYNITI_TO_DB2_TYPE_MAP.get(field_type, "VARCHAR")
        
        # Build column definition
        column = {
            "name": field_name,
            "type": db2_type,
            "nullable": allow_null,
        }
        
        # Add length/scale based on type
        if db2_type in ("CHAR", "VARCHAR", "GRAPHIC", "VARGRAPHIC"):
            column["length"] = size
        elif db2_type == "DECIMAL":
            column["length"] = precision if precision > 0 else size
            column["scale"] = scale
        elif db2_type in ("INTEGER", "SMALLINT", "BIGINT"):
            # No length needed for integer types
            pass
        
        # Add CCSID if specified
        if ccsid != 0:
            column["ccsid"] = abs(ccsid)  # Handle negative CCSID (some are negative in Syniti)
        
        # Add description
        if description:
            column["description"] = description
        
        # Add default value
        if default_value:
            # Clean up default value
            default_value = default_value.strip()
            if default_value and default_value not in ("''", "0"):
                column["default"] = default_value
        
        tables[table_id]["columns"].append(column)
        
        # Track primary keys
        if pk_pos > 0:
            tables[table_id]["primary_keys"].append((pk_pos, field_name))
    
    # Sort primary keys by position
    for table_id in tables:
        tables[table_id]["primary_keys"].sort(key=lambda x: x[0])
        tables[table_id]["primary_keys"] = [pk[1] for pk in tables[table_id]["primary_keys"]]
    
    return tables


def convert_to_qadmcli_schema(
    table_info: dict[str, Any],
    library: str,
    enable_journaling: bool = True,
) -> dict[str, Any]:
    """Convert Syniti table info to qadmcli schema format."""
    schema = {
        "table": {
            "name": table_info["name"],
            "library": library.upper(),
            "description": f"Converted from Syniti metadata - {table_info['name']}",
        },
        "columns": table_info["columns"],
    }
    
    # Add constraints
    constraints = {}
    if table_info["primary_keys"]:
        constraints["primary_key"] = {
            "columns": table_info["primary_keys"],
        }
    
    if constraints:
        schema["constraints"] = constraints
    
    # Add journaling
    if enable_journaling:
        schema["journaling"] = {
            "enabled": True,
        }
    
    return schema


def write_yaml_schema(schema: dict[str, Any], output_path: Path) -> None:
    """Write schema to YAML file."""
    # Custom YAML representer to handle formatting
    def str_representer(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
    
    yaml.add_representer(str, str_representer)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {schema['table']['name']} table\n")
        f.write(f"# Converted from Syniti metadata\n")
        f.write(f"# Library: {schema['table']['library']}\n\n")
        yaml.dump(schema, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Syniti Metadata XML to qadmcli YAML Schema"
    )
    parser.add_argument("input_xml", help="Path to Syniti metadata XML file")
    parser.add_argument(
        "--output-dir", "-o",
        default="schemas/converted",
        help="Output directory for YAML schemas (default: schemas/converted)"
    )
    parser.add_argument(
        "--library", "-l",
        default="GSLIBTST",
        help="Target library name (default: GSLIBTST)"
    )
    parser.add_argument(
        "--no-journaling",
        action="store_true",
        help="Disable journaling in generated schemas"
    )
    parser.add_argument(
        "--table", "-t",
        help="Convert only specific table (by name)"
    )
    
    args = parser.parse_args()
    
    # Parse Syniti XML
    print(f"Parsing {args.input_xml}...")
    tables = parse_syniti_xml(args.input_xml)
    print(f"Found {len(tables)} tables")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert tables
    converted_count = 0
    for table_id, table_info in tables.items():
        # Skip if specific table requested
        if args.table and table_info["name"].upper() != args.table.upper():
            continue
        
        # Skip tables with no columns
        if not table_info["columns"]:
            print(f"Skipping {table_info['name']} - no columns found")
            continue
        
        # Convert to qadmcli schema
        schema = convert_to_qadmcli_schema(
            table_info,
            args.library,
            enable_journaling=not args.no_journaling,
        )
        
        # Write YAML file
        output_file = output_dir / f"{table_info['name'].lower()}.yaml"
        write_yaml_schema(schema, output_file)
        print(f"Created: {output_file}")
        converted_count += 1
    
    print(f"\nConverted {converted_count} tables to {output_dir}")
    print(f"\nExample usage:")
    print(f"  qadmcli table create -s {output_dir}/<table>.yaml --dry-run")


if __name__ == "__main__":
    main()
