"""Table Commands Module.

This module contains all table-related CLI commands:
- table check: Check if table exists
- table create: Create table from schema
- table drop-create: Drop and recreate table
- table list: List tables in library
- table drop: Drop a table
- table empty: Delete all data from table
- table reverse: Generate YAML schema from table
- table convert: Convert schema between DB2 and MSSQL
- table create-mssql: Create MSSQL table from schema
- table compare-schemas: Compare DB2 and MSSQL schemas
"""

import sys
import logging
from typing import Optional, Any
from pathlib import Path
from datetime import datetime

import click
from rich.console import Console
from rich.text import Text

from ..config import load_config
from ..db.connection import AS400ConnectionManager, ConnectionError
from ..db.schema import SchemaManager
from ..db.mssql import MSSQLConnection, MSSQLManager
from ..models.table import TableConfig
from ..utils.logger import setup_logging
from ..utils.formatters import print_table, print_json, print_json_clean, print_ascii_panel
from ..utils.db_types import SchemaConverter, DatabaseType
from .utils import print_panel

console = Console()


@click.group()
def table():
    """Table management commands."""
    pass


@table.command("check")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library/schema name")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def table_check(ctx: click.Context, table: str, library: str, output_format: str) -> None:
    """Check if table exists and show info."""
    import logging
    logger = logging.getLogger("qadmcli")
    
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON output
    if output_format == "json":
        logger.setLevel(logging.WARNING)
    
    try:
        logger.debug(f"Loading config from: {config_path}")
        config = load_config(config_path)
        logger.debug(f"Config loaded. Host: {config.as400.host}, Library: {config.defaults.library}")
        
        with AS400ConnectionManager(config) as conn:
            logger.debug("Connected to AS400, creating SchemaManager")
            schema = SchemaManager(conn)
            
            logger.debug(f"Checking if table {library}.{table} exists")
            exists = schema.table_exists(table, library)
            logger.debug(f"Table exists: {exists}")
            
            if exists:
                logger.debug(f"Getting table info for {library}.{table}")
                info = schema.get_table_info(table, library)
                row_count = schema.get_table_row_count(table, library) if info else None
                columns = schema.get_columns(table, library) if info else []
                pk_columns = schema.get_primary_key(table, library)
                logger.debug(f"Table info retrieved successfully")
                if output_format == "json":
                    data = info.model_dump() if info else {}
                    data["row_count"] = row_count
                    data["columns"] = columns
                    data["primary_key"] = pk_columns
                    print_json_clean(data)
                else:
                    # Build text parts safely
                    # Use actual system name from info, not the input name
                    system_name = info.name if info else table
                    sql_name = info.sql_name if info else None
                    
                    parts = [
                        ("Table: ", "bold"), f"{library}.{table}", "\n",
                        ("System Name: ", "bold"), system_name, "\n",
                    ]
                    if sql_name and sql_name != system_name:
                        parts.extend([("SQL Name: ", "bold"), sql_name, "\n"])
                    parts.extend([
                        ("Exists: ", "bold"), ("Yes", "green"), "\n",
                        ("Row Count: ", "bold"), f"{row_count:,}" if row_count is not None else "N/A", "\n",
                        ("Journaled: ", "bold"), 
                    ])
                    if info and info.journaled:
                        parts.extend([("Yes", "green"), "\n"])
                        if info.journal_library and info.journal_name:
                            parts.extend([("Journal: ", "bold"), f"{info.journal_library}.{info.journal_name}", "\n"])
                    else:
                        parts.extend([("No", "yellow"), "\n"])
                    
                    # Add primary key info with identity indicator
                    if pk_columns:
                        pk_parts = []
                        for pk_col in pk_columns:
                            # Find column to check if it's identity
                            is_identity = False
                            for c in columns:
                                if c["name"] == pk_col and (c.get("is_identity") or c.get("is_generated")):
                                    is_identity = True
                                    break
                            if is_identity:
                                pk_parts.append(f"{pk_col} (auto)")
                            else:
                                pk_parts.append(pk_col)
                        parts.extend([("Primary Key: ", "bold"), ", ".join(pk_parts), "\n"])
                    else:
                        parts.extend([("Primary Key: ", "bold"), ("None", "yellow"), "\n"])
                    
                    print_panel(
                        ctx,
                        Text.assemble(*parts),
                        title="Table Information",
                        border_style="green"
                    )
                    
                    # Show columns with PK indicator, identity status, and mockup pattern
                    if columns:
                        from ..utils.data_generator import DataGenerator
                        dg = DataGenerator()
                        
                        # Use ASCII indicators when border style is ASCII
                        border_style = ctx.obj.get("border_style", "unicode")
                        if border_style == "ascii":
                            pk_indicator_char = "[PK]"
                            identity_indicator_char = "[ID]"
                        else:
                            pk_indicator_char = "🔑"
                            identity_indicator_char = "⚡"
                        
                        col_rows = []
                        for c in columns:
                            pk_indicator = pk_indicator_char if c["name"] in pk_columns else ""
                            identity_indicator = identity_indicator_char if c.get("is_identity") or c.get("is_generated") else ""
                            pattern = dg.detect_pattern(c["name"], c["type"], c.get("hint"))
                            
                            # Format CCSID display
                            ccsid_val = c.get("ccsid")
                            if ccsid_val is not None:
                                if ccsid_val == 65535:
                                    ccsid_display = "65535 (Binary)"
                                elif ccsid_val == 838:
                                    ccsid_display = "838 (Thai)"
                                elif ccsid_val == 1208:
                                    ccsid_display = "1208 (UTF-8)"
                                elif ccsid_val == 37:
                                    ccsid_display = "37 (English)"
                                else:
                                    ccsid_display = str(ccsid_val)
                            else:
                                ccsid_display = ""
                            
                            col_rows.append([
                                f"{c['name']} {pk_indicator}{identity_indicator}".strip(),
                                c["type"],
                                str(c["length"]) if c["length"] else "",
                                "Yes" if c["nullable"] else "No",
                                "Auto" if c.get("is_identity") or c.get("is_generated") else "",
                                ccsid_display,
                                pattern
                            ])
                        console.print(print_table(
                            console,
                            ["Column", "Type", "Length", "Nullable", "Identity", "CCSID", "Mockup Pattern"],
                            col_rows,
                            title=f"Columns in {library}.{table}"
                        ))
            else:
                if output_format == "json":
                    print_json_clean({"exists": False, "table": f"{library}.{table}"})
                else:
                    console.print(f"[yellow]Table {library}.{table} does not exist.[/yellow]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("create")
@click.option("--table", "-t", help="Table name (if not using schema file)")
@click.option("--library", "-l", help="Library name (if not using schema file)")
@click.option("--schema", "-s", type=click.Path(exists=True), help="Schema YAML or SQL file")
@click.option("--dry-run", is_flag=True, help="Show SQL without executing")
@click.pass_context
def table_create(ctx: click.Context, table: str | None, library: str | None, schema: str | None, dry_run: bool) -> None:
    """Create a table from schema definition."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema_mgr = SchemaManager(conn)
            
            if schema:
                schema_path = Path(schema)
                if schema_path.suffix == ".sql":
                    # Execute SQL file
                    executed = schema_mgr.execute_sql_file(str(schema_path), dry_run)
                    if dry_run:
                        console.print(f"[blue]Would execute {len(executed)} statements[/blue]")
                    else:
                        console.print(f"[green]Executed {len(executed)} statements[/green]")
                else:
                    # YAML schema
                    table_config = TableConfig.from_yaml(str(schema_path))
                    ddl = schema_mgr.create_table(table_config, dry_run)
                    if dry_run:
                        print_panel(ctx, ddl, title="SQL to Execute", border_style="blue")
                    else:
                        console.print(f"[green]Created table {table_config.library}.{table_config.name}[/green]")
            else:
                if not name or not library:
                    console.print("[red]Error: --name and --library required when not using --schema[/red]")
                    sys.exit(1)
                
                if schema_mgr.table_exists(table, library):
                    console.print(f"[yellow]Table {library}.{table} already exists.[/yellow]")
                    sys.exit(0)
                
                # Would need column definitions for simple create
                console.print("[red]Error: Use --schema for new table creation[/red]")
                sys.exit(1)
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("drop-create")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--schema", "-s", type=click.Path(exists=True), required=True, help="Schema YAML or SQL file")
@click.option("--force", "-f", is_flag=True, help="Force drop if table exists")
@click.option("--dry-run", is_flag=True, help="Show SQL without executing")
@click.pass_context
def table_drop_create(
    ctx: click.Context,
    table: str,
    library: str,
    schema: str,
    force: bool,
    dry_run: bool
) -> None:
    """Drop and recreate a table."""
    config_path = ctx.obj["config_path"]
    
    if not force and not dry_run:
        console.print("[red]Error: Use --force to confirm drop and recreate[/red]")
        sys.exit(1)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema_mgr = SchemaManager(conn)
            
            schema_path = Path(schema)
            if schema_path.suffix == ".sql":
                # Drop first
                if schema_mgr.table_exists(table, library):
                    if dry_run:
                        console.print(f"[blue]Would drop table {library}.{table}[/blue]")
                    else:
                        schema_mgr.drop_table(table, library)
                        console.print(f"[yellow]Dropped table {library}.{table}[/yellow]")
                
                # Execute SQL file
                executed = schema_mgr.execute_sql_file(str(schema_path), dry_run)
                if dry_run:
                    console.print(f"[blue]Would execute {len(executed)} statements[/blue]")
                else:
                    console.print(f"[green]Recreated table {library}.{table}[/green]")
            else:
                # YAML schema
                table_config = TableConfig.from_yaml(str(schema_path))
                ddl = schema_mgr.drop_create_table(table_config, force=True, dry_run=dry_run)
                if dry_run:
                    print_panel(ctx, ddl, title="SQL to Execute", border_style="blue")
                else:
                    console.print(f"[green]Recreated table {library}.{table}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("list")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--type", "table_type", help="Filter by table type (TABLE, VIEW, etc.)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def table_list(ctx: click.Context, library: str, table_type: str | None, output_format: str) -> None:
    """List tables in a library."""
    config_path = ctx.obj["config_path"]
    
    # Suppress logging for JSON output
    if output_format == "json":
        import logging
        logging.getLogger("qadmcli").setLevel(logging.WARNING)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            tables = schema.list_tables(library, table_type)
            
            if output_format == "json":
                print_json_clean([t.model_dump() for t in tables])
            else:
                if tables:
                    rows = []
                    for t in tables:
                        journal_info = f"{t.journal_library}.{t.journal_name}" if t.journal_library and t.journal_name else "No"
                        # Show both system name and SQL name if different
                        name_display = t.name
                        if t.sql_name and t.sql_name != t.name:
                            name_display = f"{t.name} ({t.sql_name})"
                        rows.append([name_display, t.table_type, "Yes" if t.journaled else "No", journal_info])
                    console.print(print_table(
                        console,
                        ["Table Name (System / SQL)", "Type", "Journaled", "Journal"],
                        rows,
                        title=f"Tables in {library}"
                    ))
                else:
                    console.print(f"[yellow]No tables found in {library}[/yellow]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("drop")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--cascade", "-c", is_flag=True, help="Cascade drop (remove constraints)")
@click.option("--force", "-f", is_flag=True, help="Force drop without confirmation")
@click.pass_context
def table_drop(
    ctx: click.Context,
    table: str,
    library: str,
    cascade: bool,
    force: bool
) -> None:
    """Drop a table."""
    config_path = ctx.obj["config_path"]
    
    if not force:
        console.print(f"[yellow]Warning: This will permanently delete table {library}.{table}[/yellow]")
        console.print("Use --force to confirm.")
        sys.exit(1)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            
            if not schema.table_exists(table, library):
                console.print(f"[yellow]Table {library}.{table} does not exist.[/yellow]")
                sys.exit(0)
            
            schema.drop_table(table, library, cascade)
            console.print(f"[green]Dropped table {library}.{table}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("empty")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--force", "-f", is_flag=True, help="Force delete without confirmation")
@click.pass_context
def table_empty(
    ctx: click.Context,
    table: str,
    library: str,
    force: bool
) -> None:
    """Delete all data from a table (TRUNCATE)."""
    config_path = ctx.obj["config_path"]
    
    if not force:
        console.print(f"[yellow]Warning: This will delete ALL data from {library}.{table}[/yellow]")
        console.print("Use --force to confirm.")
        sys.exit(1)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            
            if not schema.table_exists(table, library):
                console.print(f"[yellow]Table {library}.{table} does not exist.[/yellow]")
                sys.exit(1)
            
            # Get row count before truncate
            row_count = schema.get_table_row_count(table, library)
            
            # Execute TRUNCATE
            sql = f"DELETE FROM {library}.{table}"
            cursor = conn.execute(sql)
            cursor.close()
            conn.commit()
            
            console.print(f"[green]Deleted all data from {library}.{table}[/green]")
            console.print(f"Rows removed: {row_count:,}" if row_count else "Rows removed: Unknown")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("reverse")
@click.option("--table", "-t", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--output", "-o", type=click.Path(), help="Output YAML file path")
@click.pass_context
def table_reverse(
    ctx: click.Context,
    table: str,
    library: str,
    output: str | None
) -> None:
    """Generate YAML schema from existing table."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            
            if not schema.table_exists(table, library):
                console.print(f"[red]Table {library}.{table} does not exist.[/red]")
                sys.exit(1)
            
            # Generate YAML from table
            yaml_content = schema.generate_yaml_from_table(name, library)
            
            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(yaml_content)
                console.print(f"[green]Schema saved to {output}[/green]")
            else:
                print_panel(ctx, yaml_content, title=f"Schema for {library}.{table}", border_style="blue")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("convert")
@click.option("--schema", "-s", required=True, type=click.Path(exists=True), help="Source schema YAML file")
@click.option("--source-db", "-db", required=True, type=click.Choice(["DB2", "MSSQL"]), help="Source database type")
@click.option("--target-db", "-tdb", required=True, type=click.Choice(["DB2", "MSSQL"]), help="Target database type")
@click.option("--output", "-o", type=click.Path(), help="Output file for converted schema")
@click.pass_context
def table_convert(
    ctx: click.Context,
    schema: str,
    source_db: str,
    target_db: str,
    output: str | None
) -> None:
    """Convert table schema between database types."""
    try:
        import yaml

        # Load source schema
        with open(schema, "r", encoding="utf-8") as f:
            schema_data = yaml.safe_load(f)

        # Convert schema
        converter = SchemaConverter(source_db, target_db)
        converted_columns = converter.convert_schema(schema_data.get("columns", []))

        # Extract table info - support both nested (table.name) and flat (table_name) formats
        table_info = schema_data.get("table", {})
        table_name = schema_data.get("table_name") or table_info.get("name")
        library = schema_data.get("library") or table_info.get("library")
        
        # Build output schema
        output_schema = {
            "table_name": table_name,
            "library": library,
            "description": f"Converted from {source_db} to {target_db}",
            "columns": converted_columns,
        }

        # Add primary key if exists (support both formats)
        constraints = schema_data.get("constraints", {})
        primary_key = schema_data.get("primary_key") or constraints.get("primary_key")
        if primary_key:
            # Normalize to list format
            if isinstance(primary_key, dict) and "columns" in primary_key:
                output_schema["primary_key"] = primary_key["columns"]
            elif isinstance(primary_key, list):
                output_schema["primary_key"] = primary_key
            else:
                output_schema["primary_key"] = [primary_key]

        yaml_output = yaml.dump(output_schema, default_flow_style=False, allow_unicode=True, sort_keys=False)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                f.write(yaml_output)
            console.print(f"[green]Converted schema saved to {output}[/green]")
        else:
            print_panel(ctx, yaml_output, title=f"Converted Schema ({source_db} -> {target_db})", border_style="blue")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("create-mssql")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--schema", "-s", required=True, type=click.Path(exists=True), help="Schema YAML file")
@click.option("--mssql-config", "-mc", type=click.Path(exists=True), help="MSSQL connection config (defaults to connection.yaml)")
@click.option("--database", "-d", required=True, help="MSSQL database name")
@click.option("--schema-name", "-sn", default="dbo", help="MSSQL schema name (default: dbo)")
@click.option("--drop-if-exists", is_flag=True, help="Drop table if exists")
@click.option("--dry-run", is_flag=True, help="Preview SQL without executing")
@click.pass_context
def table_create_mssql(
    ctx: click.Context,
    name: str,
    schema: str,
    mssql_config: str | None,
    database: str,
    schema_name: str,
    drop_if_exists: bool,
    dry_run: bool
) -> None:
    """Create table on MSSQL from schema file."""
    config_path = mssql_config or ctx.obj["config_path"]

    try:
        import yaml
        from ..models.connection import ConnectionConfig

        # Load table schema
        with open(schema, "r", encoding="utf-8") as f:
            schema_data = yaml.safe_load(f)

        # Load MSSQL connection config
        config = load_config(Path(config_path))
        
        # Check if MSSQL is configured
        if not config.mssql:
            console.print("[red]Error: MSSQL connection not configured.[/red]")
            console.print("[yellow]Please set MSSQL_USER and MSSQL_PASSWORD environment variables[/yellow]")
            console.print("[yellow]or provide a custom config file with --mssql-config[/yellow]")
            sys.exit(1)
        
        # Create MSSQL connection config (only MSSQL part needed)
        mssql_conn_cfg = MSSQLConnectionModel(
            host=config.mssql.host,
            port=config.mssql.port,
            username=config.mssql.username,
            password=config.mssql.password,
            database=database,
        )

        # Convert schema if source is DB2
        columns = schema_data.get("columns", [])
        if schema_data.get("source_db", "DB2").upper() == "DB2":
            converter = SchemaConverter("DB2", "MSSQL")
            columns = converter.convert_schema(columns)

        if dry_run:
            # Preview SQL
            preview_conn = MSSQLConnection(mssql_conn_cfg)
            preview_mgr = MSSQLManager(preview_conn)
            sql_preview = preview_mgr.schema._build_create_sql(name, columns, schema_name, schema_data.get("primary_key"))
            # Use Text to preserve SQL brackets (avoid Rich markup interpretation)
            sql_text = Text(sql_preview, style="cyan")
            print_panel(ctx, sql_text, title="Preview SQL", border_style="yellow")
            return

        # Create table
        with MSSQLConnection(mssql_conn_cfg) as conn:
            mgr = MSSQLManager(conn)
            mgr.schema.create_table(
                table_name=name,
                columns=columns,
                schema=schema_name,
                primary_key=schema_data.get("primary_key"),
                drop_if_exists=drop_if_exists
            )
            success_text = Text.assemble(
                ("Table [", "green"),
                (f"{schema_name}.{name}", "bold cyan"),
                ("] created successfully", "green")
            )
            console.print(success_text)

    except MSSQLError as e:
        console.print(f"[red]MSSQL Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("compare-schemas")
@click.option("--db2-table", "-d2", required=True, help="DB2 table name (LIBRARY.TABLE)")
@click.option("--mssql-table", "-ms", required=True, help="MSSQL table name (SCHEMA.TABLE)")
@click.option("--mssql-config", "-mc", type=click.Path(exists=True), help="MSSQL connection config")
@click.pass_context
def table_compare_schemas(
    ctx: click.Context,
    db2_table: str,
    mssql_table: str,
    mssql_config: str | None
) -> None:
    """Compare schemas between DB2 for i and MSSQL tables."""
    config_path = ctx.obj["config_path"]

    try:
        # Parse table names
        db2_parts = db2_table.split(".")
        if len(db2_parts) != 2:
            console.print("[red]DB2 table must be in format: LIBRARY.TABLE[/red]")
            sys.exit(1)
        db2_library, db2_name = db2_parts

        mssql_parts = mssql_table.split(".")
        if len(mssql_parts) != 2:
            console.print("[red]MSSQL table must be in format: SCHEMA.TABLE[/red]")
            sys.exit(1)
        mssql_schema, mssql_name = mssql_parts

        # Load configs
        config = load_config(config_path)

        # Get DB2 schema
        with AS400ConnectionManager(config) as conn:
            schema_mgr = SchemaManager(conn)
            db2_columns = schema_mgr.get_columns(db2_name, db2_library)

        # Get MSSQL schema
        mssql_cfg = load_config(Path(mssql_config) if mssql_config else config_path)
        
        # Check if MSSQL is configured
        if not mssql_cfg.mssql:
            console.print("[red]Error: MSSQL connection not configured.[/red]")
            console.print("[yellow]Please set MSSQL_USER and MSSQL_PASSWORD environment variables[/yellow]")
            console.print("[yellow]or provide a custom config file with --mssql-config[/yellow]")
            sys.exit(1)
        
        mssql_conn_cfg = MSSQLConnectionModel(
            host=mssql_cfg.mssql.host,
            port=mssql_cfg.mssql.port,
            username=mssql_cfg.mssql.username,
            password=mssql_cfg.mssql.password,
            database=mssql_cfg.mssql.database,
        )

        with MSSQLConnection(mssql_conn_cfg) as conn:
            mssql_mgr = MSSQLManager(conn)
            mssql_columns = mssql_mgr.schema.get_columns(mssql_name, mssql_schema)

        # Compare schemas with fuzzy matching
        converter = SchemaConverter("DB2", "MSSQL")
        mismatches = []
        side_by_side = []

        # Build fuzzy matching key (remove underscores, normalize)
        def normalize_key(name: str) -> str:
            """Normalize column name for fuzzy matching."""
            return name.upper().replace("_", "").replace(" ", "")
        
        # Create maps
        db2_col_map = {col["name"].upper(): col for col in db2_columns}
        mssql_col_map = {col["name"].upper(): col for col in mssql_columns}
        db2_fuzzy_map = {normalize_key(col["name"]): col for col in db2_columns}
        mssql_fuzzy_map = {normalize_key(col["name"]): col for col in mssql_columns}
        
        # Track processed columns
        db2_processed = set()
        mssql_processed = set()
        
        # First pass: exact matches
        for col_name_upper in sorted(db2_col_map.keys() & mssql_col_map.keys()):
            db2_col = db2_col_map[col_name_upper]
            mssql_col = mssql_col_map[col_name_upper]
            db2_processed.add(col_name_upper)
            mssql_processed.add(col_name_upper)
            
            db2_type = DatabaseType(
                db_type=db2_col["type"],
                length=db2_col.get("length"),
                scale=db2_col.get("scale"),
                nullable=db2_col.get("nullable", True)
            )
            expected_mssql = converter.convert_column(db2_col["name"], db2_type)
            
            type_match = expected_mssql.db_type == mssql_col["type"]
            null_match = db2_col.get("nullable", True) == mssql_col.get("nullable", True)
            
            db2_type_str = f"{db2_col['type']}"
            if db2_col.get('length'):
                db2_type_str += f"({db2_col['length']}"
                if db2_col.get('scale'):
                    db2_type_str += f",{db2_col['scale']}"
                db2_type_str += ")"
            
            mssql_type_str = f"{mssql_col['type']}"
            if mssql_col.get('length'):
                mssql_type_str += f"({mssql_col['length']}"
                if mssql_col.get('scale'):
                    mssql_type_str += f",{mssql_col['scale']}"
                mssql_type_str += ")"
            
            if type_match and null_match:
                status = "[green]OK Match[/green]"
            else:
                status_parts = []
                if not type_match:
                    status_parts.append(f"Type: {expected_mssql.db_type}≠{mssql_col['type']}")
                    mismatches.append(
                        f"Column '{db2_col['name']}' type mismatch: DB2({db2_col['type']}) -> "
                        f"Expected MSSQL({expected_mssql.db_type}), Got MSSQL({mssql_col['type']})"
                    )
                if not null_match:
                    status_parts.append("Null mismatch")
                    mismatches.append(
                        f"Column '{db2_col['name']}' nullable mismatch: DB2({db2_col.get('nullable')}) vs "
                        f"MSSQL({mssql_col.get('nullable')})"
                    )
                status = f"[red]{' | '.join(status_parts)}[/red]"
            
            side_by_side.append({
                "column": db2_col["name"],
                "db2_type": db2_type_str,
                "db2_null": "Y" if db2_col.get('nullable') else "N",
                "mssql_type": mssql_type_str,
                "mssql_null": "Y" if mssql_col.get('nullable') else "N",
                "status": status
            })
        
        # Second pass: fuzzy matches (columns that normalize to same key)
        for db2_col in db2_columns:
            db2_name_upper = db2_col["name"].upper()
            if db2_name_upper in db2_processed:
                continue
            
            fuzzy_key = normalize_key(db2_col["name"])
            mssql_col = mssql_fuzzy_map.get(fuzzy_key)
            
            if mssql_col and mssql_col["name"].upper() not in mssql_processed:
                mssql_name_upper = mssql_col["name"].upper()
                db2_processed.add(db2_name_upper)
                mssql_processed.add(mssql_name_upper)
                
                db2_type = DatabaseType(
                    db_type=db2_col["type"],
                    length=db2_col.get("length"),
                    scale=db2_col.get("scale"),
                    nullable=db2_col.get("nullable", True)
                )
                expected_mssql = converter.convert_column(db2_col["name"], db2_type)
                
                type_match = expected_mssql.db_type == mssql_col["type"]
                null_match = db2_col.get("nullable", True) == mssql_col.get("nullable", True)
                
                db2_type_str = f"{db2_col['type']}"
                if db2_col.get('length'):
                    db2_type_str += f"({db2_col['length']}"
                    if db2_col.get('scale'):
                        db2_type_str += f",{db2_col['scale']}"
                    db2_type_str += ")"
                
                mssql_type_str = f"{mssql_col['type']}"
                if mssql_col.get('length'):
                    mssql_type_str += f"({mssql_col['length']}"
                    if mssql_col.get('scale'):
                        mssql_type_str += f",{mssql_col['scale']}"
                    mssql_type_str += ")"
                
                if type_match and null_match:
                    status = "[yellow]~ Fuzzy Match[/yellow]"
                else:
                    status_parts = []
                    if not type_match:
                        status_parts.append(f"Type: {expected_mssql.db_type}≠{mssql_col['type']}")
                        mismatches.append(
                            f"Fuzzy column '{db2_col['name']}↔{mssql_col['name']}' type mismatch"
                        )
                    if not null_match:
                        status_parts.append("Null mismatch")
                        mismatches.append(
                            f"Fuzzy column '{db2_col['name']}↔{mssql_col['name']}' nullable mismatch"
                        )
                    status = f"[red]{' | '.join(status_parts)}[/red]"
                
                side_by_side.append({
                    "column": f"{db2_col['name']}↔{mssql_col['name']}",
                    "db2_type": db2_type_str,
                    "db2_null": "Y" if db2_col.get('nullable') else "N",
                    "mssql_type": mssql_type_str,
                    "mssql_null": "Y" if mssql_col.get('nullable') else "N",
                    "status": status
                })
        
        # Third pass: unmatched columns
        for db2_col in db2_columns:
            if db2_col["name"].upper() not in db2_processed:
                side_by_side.append({
                    "column": db2_col["name"],
                    "db2_type": f"[cyan]{db2_col['type']}[/cyan]",
                    "db2_null": "Y" if db2_col.get('nullable') else "N",
                    "mssql_type": "[red]N/A[/red]",
                    "mssql_null": "",
                    "status": "[red]DB2 Only[/red]"
                })
                mismatches.append(f"Column '{db2_col['name']}' exists in DB2 but not in MSSQL")
        
        for mssql_col in mssql_columns:
            if mssql_col["name"].upper() not in mssql_processed:
                side_by_side.append({
                    "column": mssql_col["name"],
                    "db2_type": "[red]N/A[/red]",
                    "db2_null": "",
                    "mssql_type": f"[cyan]{mssql_col['type']}[/cyan]",
                    "mssql_null": "Y" if mssql_col.get('nullable') else "N",
                    "status": "[red]MSSQL Only[/red]"
                })
                mismatches.append(f"Column '{mssql_col['name']}' exists in MSSQL but not in DB2")

        # Display side-by-side table
        from rich.table import Table
        from rich import box
        table = Table(title=f"Schema Comparison: {db2_table} vs {mssql_table}", box=box.ASCII)
        table.add_column("Column", style="bold")
        table.add_column("DB2 Type", justify="left")
        table.add_column("N", justify="center")
        table.add_column("MSSQL Type", justify="left")
        table.add_column("N", justify="center")
        table.add_column("Status", justify="left")
        
        for row in side_by_side:
            table.add_row(
                row["column"],
                row["db2_type"],
                row["db2_null"],
                row["mssql_type"],
                row["mssql_null"],
                row["status"]
            )
        
        console.print(table)
        
        # Summary
        total_columns = len(db2_columns) + len(mssql_columns) - len([r for r in side_by_side if "Match" in r["status"]])
        if mismatches:
            console.print(f"\n[red]Found {len(mismatches)} difference(s)[/red]")
        else:
            console.print(f"\n[green]✓ Schemas match! {len(side_by_side)} column pair(s) are compatible.[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)



def register_table_commands(cli_group):
    """Register table commands with the main CLI group."""
    cli_group.add_command(table)
