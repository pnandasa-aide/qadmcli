#!/usr/bin/env python3
"""Analyze Syniti metadata structure - connections, schemas, tables."""

import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


def main():
    xml_path = Path("schemas/syniti/MetaData_20230608.xml")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Get connection info
    print("=" * 60)
    print("CONNECTIONS (DBMMConnections)")
    print("=" * 60)
    connections = {}
    for conn in root.findall('.//DBMMConnections'):
        conn_id = int(conn.findtext('ConnectionID', '0'))
        name = conn.findtext('Name', '')
        is_source = conn.findtext('IsSource', 'N') == 'Y'
        conn_type = conn.findtext('Type', '')
        # Type mapping based on Syniti documentation
        type_names = {'1': 'SQL Server', '2': 'Oracle', '3': 'DB2', '4': 'MySQL', '5': 'PostgreSQL'}
        type_name = type_names.get(conn_type, f'Unknown({conn_type})')
        
        connections[conn_id] = {
            'name': name, 
            'is_source': is_source, 
            'type': conn_type,
            'type_name': type_name
        }
        source_flag = 'SOURCE >>' if is_source else 'TARGET'
        print(f"  Connection {conn_id}: {name}")
        print(f"    Type: {type_name} ({conn_type})")
        print(f"    Role: {source_flag}")
    
    # Get schema info
    print()
    print("=" * 60)
    print("SCHEMAS (DBMMSchemas)")
    print("=" * 60)
    schemas = {}
    for schema in root.findall('.//DBMMSchemas'):
        schema_id = int(schema.findtext('SchemaID', '0'))
        conn_id = int(schema.findtext('ConnectionID', '0'))
        name = schema.findtext('Name', '')
        schemas[schema_id] = {'name': name, 'connection_id': conn_id}
        conn_name = connections.get(conn_id, {}).get('name', f'Conn_{conn_id}')
        print(f"  Schema {schema_id}: '{name}' (Connection: {conn_name})")
    
    # Get catalog info (for SQL Server multi-database)
    print()
    print("=" * 60)
    print("CATALOGS (DBMMCatalogs) - SQL Server Databases")
    print("=" * 60)
    catalogs = {}
    for cat in root.findall('.//DBMMCatalogs'):
        cat_id = int(cat.findtext('CatalogID', '0'))
        conn_id = int(cat.findtext('ConnectionID', '0'))
        name = cat.findtext('Name', '')
        catalogs[cat_id] = {'name': name, 'connection_id': conn_id}
        conn_name = connections.get(conn_id, {}).get('name', f'Conn_{conn_id}')
        print(f"  Catalog {cat_id}: '{name}' (Connection: {conn_name})")
    
    # Group tables by connection and schema
    print()
    print("=" * 60)
    print("TABLES BY CONNECTION/SCHEMA")
    print("=" * 60)
    
    tables_by_conn = defaultdict(lambda: defaultdict(list))
    source_tables = []
    target_tables = []
    
    for table in root.findall('.//DBMMTables'):
        table_id = int(table.findtext('TableID', '0'))
        conn_id = int(table.findtext('ConnectionID', '0'))
        schema_id = int(table.findtext('SchemaID', '0'))
        catalog_id = int(table.findtext('CatalogID', '0')) if table.find('CatalogID') is not None else 0
        name = table.findtext('Name', '')
        
        schema_name = schemas.get(schema_id, {}).get('name', f'Schema_{schema_id}')
        catalog_name = catalogs.get(catalog_id, {}).get('name', '') if catalog_id else ''
        
        # Build qualified name
        if catalog_name:
            qualified_name = f"{catalog_name}.{schema_name}.{name}"
        else:
            qualified_name = f"{schema_name}.{name}"
        
        tables_by_conn[conn_id][schema_name].append({
            'name': name,
            'qualified': qualified_name,
            'table_id': table_id
        })
        
        if connections.get(conn_id, {}).get('is_source'):
            source_tables.append({
                'name': name,
                'qualified': qualified_name,
                'connection': connections[conn_id]['name'],
                'schema': schema_name
            })
        else:
            target_tables.append({
                'name': name,
                'qualified': qualified_name,
                'connection': connections[conn_id]['name'],
                'schema': schema_name
            })
    
    # Print tables by connection
    for conn_id, conn_info in sorted(connections.items()):
        source_flag = 'SOURCE' if conn_info['is_source'] else 'TARGET'
        print(f"\nConnection {conn_id}: {conn_info['name']} ({source_flag})")
        
        if conn_id in tables_by_conn:
            for schema_name, table_list in sorted(tables_by_conn[conn_id].items()):
                print(f"  Schema '{schema_name}': {len(table_list)} tables")
                # Show first 5 tables as sample
                for t in table_list[:5]:
                    print(f"    - {t['name']}")
                if len(table_list) > 5:
                    print(f"    ... and {len(table_list) - 5} more")
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Source tables (DB2): {len(source_tables)}")
    print(f"Target tables (MSSQL): {len(target_tables)}")
    print(f"Total unique table names: {len(set(t['name'] for t in source_tables + target_tables))}")
    
    # Check for duplicates in source
    source_names = [t['name'] for t in source_tables]
    duplicates = {name: source_names.count(name) for name in set(source_names) if source_names.count(name) > 1}
    if duplicates:
        print(f"\nDuplicate tables in SOURCE (same name, different schema):")
        for name, count in sorted(duplicates.items()):
            schemas_for_table = [t['schema'] for t in source_tables if t['name'] == name]
            print(f"  {name}: appears {count} times in schemas {schemas_for_table}")
    
    # Show source table list (for conversion)
    print()
    print("=" * 60)
    print("SOURCE TABLES FOR CONVERSION (DB2)")
    print("=" * 60)
    print(f"Total: {len(source_tables)} tables")
    print("\nFirst 20 source tables:")
    for t in source_tables[:20]:
        print(f"  - {t['qualified']}")


if __name__ == "__main__":
    main()
