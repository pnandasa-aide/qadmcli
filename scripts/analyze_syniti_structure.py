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
    
    # Visual Tree Representation
    print()
    print("=" * 60)
    print("VISUAL HIERARCHY TREE")
    print("=" * 60)
    
    for conn_id, conn_info in sorted(connections.items()):
        source_flag = "[SOURCE]" if conn_info["is_source"] else "[TARGET]"
        conn_type_name = "DB2" if conn_info["type"] == "3" else "MSSQL" if conn_info["type"] == "1" else f"Type{conn_info['type']}"
        print(f"\n📡 Connection {conn_id}: {conn_info['name']} {source_flag} ({conn_type_name})")
        
        if conn_id not in tables_by_conn:
            print("   └─ (no tables)")
            continue
        
        # For DB2 (source), group by schema
        if conn_info["type"] == "3":  # DB2
            schema_groups = tables_by_conn[conn_id]
            schema_list = sorted(schema_groups.keys())
            
            for i, schema_name in enumerate(schema_list):
                is_last_schema = (i == len(schema_list) - 1)
                schema_prefix = "   └─" if is_last_schema else "   ├─"
                table_list = schema_groups[schema_name]
                
                print(f"{schema_prefix} 📁 Schema: {schema_name} ({len(table_list)} tables)")
                
                # Show sample tables (first 3)
                for j, t in enumerate(table_list[:3]):
                    is_last_table = (j == len(table_list[:3]) - 1) and len(table_list) <= 3
                    table_prefix = "      └─" if is_last_table else "      ├─"
                    print(f"{table_prefix} 📝 {t['name']}")
                
                if len(table_list) > 3:
                    print(f"      └─ ... and {len(table_list) - 3} more tables")
        
        # For MSSQL (target), group by catalog then schema
        else:  # MSSQL
            # Group by catalog
            catalogs_for_conn = {}
            for schema_name, table_list in tables_by_conn[conn_id].items():
                # Find catalog for this schema
                cat_name = "default"
                for cat_id, cat_info in catalogs.items():
                    if cat_info["connection_id"] == conn_id:
                        cat_name = cat_info["name"]
                        break
                if cat_name not in catalogs_for_conn:
                    catalogs_for_conn[cat_name] = {}
                catalogs_for_conn[cat_name][schema_name] = table_list
            
            cat_list = sorted(catalogs_for_conn.keys())
            for k, cat_name in enumerate(cat_list):
                is_last_cat = (k == len(cat_list) - 1)
                cat_prefix = "   └─" if is_last_cat else "   ├─"
                schema_groups = catalogs_for_conn[cat_name]
                total_tables = sum(len(t) for t in schema_groups.values())
                
                print(f"{cat_prefix} 🗄️  Catalog (Database): {cat_name} ({total_tables} tables)")
                
                schema_list = sorted(schema_groups.keys())
                for i, schema_name in enumerate(schema_list):
                    is_last_schema = (i == len(schema_list) - 1)
                    schema_prefix = "      └─" if is_last_schema else "      ├─"
                    table_list = schema_groups[schema_name]
                    
                    print(f"{schema_prefix} 📁 Schema: {schema_name} ({len(table_list)} tables)")
                    
                    # Show sample tables
                    for j, t in enumerate(table_list[:2]):
                        is_last_table = (j == len(table_list[:2]) - 1) and len(table_list) <= 2
                        table_prefix = "         └─" if is_last_table else "         ├─"
                        print(f"{table_prefix} 📝 {t['name']}")
                    
                    if len(table_list) > 2:
                        print(f"         └─ ... and {len(table_list) - 2} more tables")
    
    # Summary Statistics
    print()
    print("=" * 60)
    print("SUMMARY STATISTICS")
    print("=" * 60)
    
    for conn_id, conn_info in sorted(connections.items()):
        if conn_id in tables_by_conn:
            total_tables = sum(len(t) for t in tables_by_conn[conn_id].values())
            schema_count = len(tables_by_conn[conn_id])
            print(f"\n{conn_info['name']}:")
            print(f"  Total Tables: {total_tables}")
            print(f"  Schemas: {schema_count}")
            
            # Top 5 largest schemas
            sorted_schemas = sorted(
                tables_by_conn[conn_id].items(),
                key=lambda x: len(x[1]),
                reverse=True
            )[:5]
            print(f"  Top 5 Largest Schemas:")
            for schema_name, table_list in sorted_schemas:
                print(f"    - {schema_name}: {len(table_list)} tables")


if __name__ == "__main__":
    main()
