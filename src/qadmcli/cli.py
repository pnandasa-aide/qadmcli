"""QADM CLI - Main entry point."""

import os
import sys
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .config import load_config
from .db.connection import AS400ConnectionManager, ConnectionError
from .db.schema import SchemaManager
from .db.journal import JournalManager
from .db.mssql import MSSQLConnection, MSSQLManager, MSSQLError
from .models.connection import MSSQLConnection as MSSQLConnectionModel
from .models.table import TableConfig
from .utils.logger import setup_logging
from .utils.formatters import print_table, print_json, print_ascii_panel
from .utils.db_types import SchemaConverter, DatabaseType

console = Console()

# Default config path
DEFAULT_CONFIG = Path("config/connection.yaml")


def get_config_path(ctx: click.Context, param: Any, value: str | None) -> Path:
    """Resolve config path."""
    if value:
        path = Path(value)
    else:
        # Try environment variable first
        env_config = os.environ.get("QADMCLI_CONFIG")
        if env_config:
            path = Path(env_config)
        else:
            path = DEFAULT_CONFIG
    
    if not path.exists():
        raise click.BadParameter(f"Config file not found: {path}")
    
    return path


@click.group()
@click.version_option(version=__version__, prog_name="qadmcli")
@click.option(
    "--config", "-c",
    type=click.Path(exists=True, path_type=Path),
    callback=get_config_path,
    help="Path to connection config file (default: config/connection.yaml)"
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--json", "output_json", is_flag=True, help="Output in JSON format")
@click.pass_context
def cli(ctx: click.Context, config: Path, verbose: bool, output_json: bool) -> None:
    """QADM CLI - AS400 DB2 for i Database Management Tool."""
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Store options in context
    ctx.obj["config_path"] = config
    ctx.obj["verbose"] = verbose
    ctx.obj["output_json"] = output_json
    
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level)


@cli.group()
def connection() -> None:
    """Connection management commands."""
    pass


@connection.command("test")
@click.pass_context
def connection_test(ctx: click.Context) -> None:
    """Test connection to AS400."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            info = conn.test_connection()
        
        if output_json:
            print_json(console, info)
        else:
            console.print(Panel(
                Text.assemble(
                    ("Host: ", "bold"), info["host"], "\n",
                    ("Status: ", "bold"), ("Connected", "green"), "\n",
                    ("Version: ", "bold"), info["server_info"].get("version", "N/A"),
                ),
                title="Connection Test",
                border_style="green"
            ))
        
    except ConnectionError as e:
        console.print(Panel(
            Text.assemble(("Error: ", "bold red"), e.message),
            title="Connection Failed",
            border_style="red"
        ))
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.group()
def table() -> None:
    """Table management commands."""
    pass


@table.command("check")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library/schema name")
@click.pass_context
def table_check(ctx: click.Context, name: str, library: str) -> None:
    """Check if table exists and show info."""
    import logging
    logger = logging.getLogger("qadmcli")
    
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        logger.debug(f"Loading config from: {config_path}")
        config = load_config(config_path)
        logger.debug(f"Config loaded. Host: {config.as400.host}, Library: {config.defaults.library}")
        
        with AS400ConnectionManager(config) as conn:
            logger.debug("Connected to AS400, creating SchemaManager")
            schema = SchemaManager(conn)
            
            logger.debug(f"Checking if table {library}.{name} exists")
            exists = schema.table_exists(name, library)
            logger.debug(f"Table exists: {exists}")
            
            if exists:
                logger.debug(f"Getting table info for {library}.{name}")
                info = schema.get_table_info(name, library)
                row_count = schema.get_table_row_count(name, library) if info else None
                columns = schema.get_columns(name, library) if info else []
                pk_columns = schema.get_primary_key(name, library)
                logger.debug(f"Table info retrieved successfully")
                if output_json:
                    data = info.model_dump() if info else {}
                    data["row_count"] = row_count
                    data["columns"] = columns
                    data["primary_key"] = pk_columns
                    print_json(console, data)
                else:
                    # Build text parts safely
                    parts = [
                        ("Table: ", "bold"), f"{library}.{name}", "\n",
                        ("System Name: ", "bold"), name, "\n",
                    ]
                    if info and info.sql_name and info.sql_name != name:
                        parts.extend([("SQL Name: ", "bold"), info.sql_name, "\n"])
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
                    
                    # Add primary key info
                    if pk_columns:
                        parts.extend([("Primary Key: ", "bold"), ", ".join(pk_columns), "\n"])
                    else:
                        parts.extend([("Primary Key: ", "bold"), ("None", "yellow"), "\n"])
                    
                    console.print(Panel(
                        Text.assemble(*parts),
                        title="Table Information",
                        border_style="green"
                    ))
                    
                    # Show columns with PK indicator and mockup pattern
                    if columns:
                        from .utils.data_generator import DataGenerator
                        dg = DataGenerator()
                        
                        col_rows = []
                        for c in columns:
                            pk_indicator = "🔑" if c["name"] in pk_columns else ""
                            pattern = dg.detect_pattern(c["name"], c["type"], c.get("hint"))
                            col_rows.append([
                                f"{c['name']} {pk_indicator}".strip(),
                                c["type"],
                                str(c["length"]) if c["length"] else "",
                                "Yes" if c["nullable"] else "No",
                                pattern
                            ])
                        console.print(print_table(
                            console,
                            ["Column", "Type", "Length", "Nullable", "Mockup Pattern"],
                            col_rows,
                            title=f"Columns in {library}.{name}"
                        ))
            else:
                if output_json:
                    print_json(console, {"exists": False, "table": f"{library}.{name}"})
                else:
                    console.print(f"[yellow]Table {library}.{name} does not exist.[/yellow]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("create")
@click.option("--name", "-n", help="Table name (if not using schema file)")
@click.option("--library", "-l", help="Library name (if not using schema file)")
@click.option("--schema", "-s", type=click.Path(exists=True), help="Schema YAML or SQL file")
@click.option("--dry-run", is_flag=True, help="Show SQL without executing")
@click.pass_context
def table_create(ctx: click.Context, name: str | None, library: str | None, schema: str | None, dry_run: bool) -> None:
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
                        console.print(Panel(ddl, title="SQL to Execute", border_style="blue"))
                    else:
                        console.print(f"[green]Created table {table_config.library}.{table_config.name}[/green]")
            else:
                if not name or not library:
                    console.print("[red]Error: --name and --library required when not using --schema[/red]")
                    sys.exit(1)
                
                if schema_mgr.table_exists(name, library):
                    console.print(f"[yellow]Table {library}.{name} already exists.[/yellow]")
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
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--schema", "-s", type=click.Path(exists=True), required=True, help="Schema YAML or SQL file")
@click.option("--force", "-f", is_flag=True, help="Force drop if table exists")
@click.option("--dry-run", is_flag=True, help="Show SQL without executing")
@click.pass_context
def table_drop_create(
    ctx: click.Context,
    name: str,
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
                if schema_mgr.table_exists(name, library):
                    if dry_run:
                        console.print(f"[blue]Would drop table {library}.{name}[/blue]")
                    else:
                        schema_mgr.drop_table(name, library)
                        console.print(f"[yellow]Dropped table {library}.{name}[/yellow]")
                
                # Execute SQL file
                executed = schema_mgr.execute_sql_file(str(schema_path), dry_run)
                if dry_run:
                    console.print(f"[blue]Would execute {len(executed)} statements[/blue]")
                else:
                    console.print(f"[green]Recreated table {library}.{name}[/green]")
            else:
                # YAML schema
                table_config = TableConfig.from_yaml(str(schema_path))
                ddl = schema_mgr.drop_create_table(table_config, force=True, dry_run=dry_run)
                if dry_run:
                    console.print(Panel(ddl, title="SQL to Execute", border_style="blue"))
                else:
                    console.print(f"[green]Recreated table {library}.{name}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("list")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--type", "table_type", help="Filter by table type (TABLE, VIEW, etc.)")
@click.pass_context
def table_list(ctx: click.Context, library: str, table_type: str | None) -> None:
    """List tables in a library."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            tables = schema.list_tables(library, table_type)
            
            if output_json:
                print_json(console, [t.model_dump() for t in tables])
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
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--cascade", "-c", is_flag=True, help="Cascade drop (remove constraints)")
@click.option("--force", "-f", is_flag=True, help="Force drop without confirmation")
@click.pass_context
def table_drop(
    ctx: click.Context,
    name: str,
    library: str,
    cascade: bool,
    force: bool
) -> None:
    """Drop a table."""
    config_path = ctx.obj["config_path"]
    
    if not force:
        console.print(f"[yellow]Warning: This will permanently delete table {library}.{name}[/yellow]")
        console.print("Use --force to confirm.")
        sys.exit(1)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            
            if not schema.table_exists(name, library):
                console.print(f"[yellow]Table {library}.{name} does not exist.[/yellow]")
                sys.exit(0)
            
            schema.drop_table(name, library, cascade)
            console.print(f"[green]Dropped table {library}.{name}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("empty")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--force", "-f", is_flag=True, help="Force delete without confirmation")
@click.pass_context
def table_empty(
    ctx: click.Context,
    name: str,
    library: str,
    force: bool
) -> None:
    """Delete all data from a table (TRUNCATE)."""
    config_path = ctx.obj["config_path"]
    
    if not force:
        console.print(f"[yellow]Warning: This will delete ALL data from {library}.{name}[/yellow]")
        console.print("Use --force to confirm.")
        sys.exit(1)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            
            if not schema.table_exists(name, library):
                console.print(f"[yellow]Table {library}.{name} does not exist.[/yellow]")
                sys.exit(1)
            
            # Get row count before truncate
            row_count = schema.get_table_row_count(name, library)
            
            # Execute TRUNCATE
            sql = f"DELETE FROM {library}.{name}"
            cursor = conn.execute(sql)
            cursor.close()
            conn.commit()
            
            console.print(f"[green]Deleted all data from {library}.{name}[/green]")
            console.print(f"Rows removed: {row_count:,}" if row_count else "Rows removed: Unknown")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@table.command("reverse")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--output", "-o", type=click.Path(), help="Output YAML file path")
@click.pass_context
def table_reverse(
    ctx: click.Context,
    name: str,
    library: str,
    output: str | None
) -> None:
    """Generate YAML schema from existing table."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            
            if not schema.table_exists(name, library):
                console.print(f"[red]Table {library}.{name} does not exist.[/red]")
                sys.exit(1)
            
            # Generate YAML from table
            yaml_content = schema.generate_yaml_from_table(name, library)
            
            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(yaml_content)
                console.print(f"[green]Schema saved to {output}[/green]")
            else:
                console.print(Panel(yaml_content, title=f"Schema for {library}.{name}", border_style="blue"))
        
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
            console.print(Panel(yaml_output, title=f"Converted Schema ({source_db} -> {target_db})", border_style="blue"))

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
        from .models.connection import ConnectionConfig

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
            console.print(Panel(sql_text, title="Preview SQL", border_style="yellow"))
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


@cli.group()
def journal() -> None:
    """Journal management commands."""
    pass


@journal.command("check")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.pass_context
def journal_check(ctx: click.Context, name: str, library: str) -> None:
    """Check journal status for a table."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            info = jrn.get_journal_info(name, library)
            
            if output_json:
                print_json(console, info.get_summary())
            else:
                status_color = "green" if info.is_journaled else "yellow"
                console.print(Panel(
                    Text.assemble(
                        ("Table: ", "bold"), f"{library}.{name}", "\n",
                        ("Journaled: ", "bold"), ("Yes" if info.is_journaled else "No", status_color), "\n",
                        ("Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library and info.journal_name else "N/A"), "\n",
                        ("Receiver: ", "bold"), (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library and info.journal_receiver_name else "N/A"), "\n",
                        ("Entry Range: ", "bold"), 
                        (f"{info.oldest_entry_sequence} - {info.newest_entry_sequence}" if info.oldest_entry_sequence and info.newest_entry_sequence else "N/A"),
                    ),
                    title="Journal Information",
                    border_style=status_color
                ))
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("disable")
@click.option("--name", "-n", required=True, help="Table name (supports wildcards: * or %)")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--dry-run", is_flag=True, help="Show which tables would be affected without making changes")
@click.pass_context
def journal_disable(
    ctx: click.Context,
    name: str,
    library: str,
    dry_run: bool
) -> None:
    """Disable journaling for one or more tables.
    
    Supports wildcards:
      - * or % for multiple characters
      - ? or _ for single character
    
    Examples:
      qadmcli journal disable -n TB_01 -l EZPIPE
      qadmcli journal disable -n "TB_*" -l EZPIPE
      qadmcli journal disable -n "%TEST%" -l MYLIB --dry-run
    """
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Check if wildcard pattern (* and ? are shell-style, % is SQL-style)
            # Note: _ is a valid character in IBM i table names, not a wildcard
            if '*' in name or '%' in name or '?' in name:
                # Find matching tables
                from .db.schema import SchemaManager
                import fnmatch
                schema_mgr = SchemaManager(conn)
                all_tables = schema_mgr.list_tables(library)
                
                # Filter tables by pattern (convert SQL wildcards to fnmatch pattern)
                pattern = name.replace('%', '*').replace('_', '?')
                tables = [t for t in all_tables if fnmatch.fnmatch(t.name, pattern)]
                
                if not tables:
                    console.print(f"[yellow]No tables matching pattern '{name}' in {library}[/yellow]")
                    return
                
                if dry_run:
                    console.print(f"[blue]Dry run - would disable journaling for {len(tables)} table(s):[/blue]")
                    for table in tables:
                        console.print(f"  - {table.name}")
                    return
                
                # Process each table
                results = []
                success_count = 0
                error_count = 0
                
                console.print(f"[blue]Disabling journaling for {len(tables)} table(s)...[/blue]")
                for table in tables:
                    try:
                        result = jrn.disable_journaling(table.name, library)
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": True
                        })
                        success_count += 1
                        console.print(f"  [green]OK[/green] {library}.{table.name}")
                    except Exception as e:
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": False,
                            "error": str(e)
                        })
                        error_count += 1
                        console.print(f"  [red]ERR[/red] {library}.{table.name}: {e}")
                
                if output_json:
                    print_json(console, {
                        "operation": "disable",
                        "pattern": name,
                        "library": library,
                        "total": len(tables),
                        "success": success_count,
                        "errors": error_count,
                        "results": results
                    })
                else:
                    console.print(f"\n[green]Completed: {success_count} succeeded, {error_count} failed[/green]")
            else:
                # Single table
                if dry_run:
                    console.print(f"[blue]Dry run - would disable journaling for {library}.{name}[/blue]")
                    return
                
                result = jrn.disable_journaling(name, library)
                
                if output_json:
                    print_json(console, result)
                else:
                    console.print(f"[green]Disabled journaling for {library}.{name}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("enable")
@click.option("--name", "-n", required=True, help="Table name (supports wildcards: * or %)")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--journal-library", "-j", help="Journal library (default from config)")
@click.option("--journal-name", help="Journal name (default: QSQJRN)")
@click.option("--images", "-i", type=click.Choice(["*BOTH", "*AFTER", "*BEFORE"]), 
              default="*AFTER", help="Journal images to capture (default: *AFTER)")
@click.option("--dry-run", is_flag=True, help="Show which tables would be affected without making changes")
@click.pass_context
def journal_enable(
    ctx: click.Context,
    name: str,
    library: str,
    journal_library: str | None,
    journal_name: str | None,
    images: str,
    dry_run: bool
) -> None:
    """Enable journaling for one or more tables.
    
    Supports wildcards:
      - * or % for multiple characters
      - ? or _ for single character
    
    Examples:
      qadmcli journal enable -n TB_01 -l EZPIPE
      qadmcli journal enable -n "TB_*" -l EZPIPE --images *BOTH
      qadmcli journal enable -n "%TEST%" -l MYLIB -j MYLIB --dry-run
    """
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Check if wildcard pattern (* and ? are shell-style, % is SQL-style)
            # Note: _ is a valid character in IBM i table names, not a wildcard
            if '*' in name or '%' in name or '?' in name:
                # Find matching tables
                from .db.schema import SchemaManager
                import fnmatch
                schema_mgr = SchemaManager(conn)
                all_tables = schema_mgr.list_tables(library)
                
                # Filter tables by pattern (convert SQL wildcards to fnmatch pattern)
                pattern = name.replace('%', '*').replace('_', '?')
                tables = [t for t in all_tables if fnmatch.fnmatch(t.name, pattern)]
                
                if not tables:
                    console.print(f"[yellow]No tables matching pattern '{name}' in {library}[/yellow]")
                    return
                
                if dry_run:
                    console.print(f"[blue]Dry run - would enable journaling for {len(tables)} table(s):[/blue]")
                    for table in tables:
                        console.print(f"  - {table.name} (images: {images})")
                    return
                
                # Process each table
                results = []
                success_count = 0
                error_count = 0
                
                console.print(f"[blue]Enabling journaling for {len(tables)} table(s) with {images}...[/blue]")
                for table in tables:
                    try:
                        result = jrn.enable_journaling(table.name, library, journal_library, journal_name, images)
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": True,
                            "journal": result['journal']
                        })
                        success_count += 1
                        console.print(f"  [green]OK[/green] {library}.{table.name} -> {result['journal']}")
                    except Exception as e:
                        results.append({
                            "table": f"{library}.{table.name}",
                            "success": False,
                            "error": str(e)
                        })
                        error_count += 1
                        console.print(f"  [red]ERR[/red] {library}.{table.name}: {e}")
                
                if output_json:
                    print_json(console, {
                        "operation": "enable",
                        "pattern": name,
                        "library": library,
                        "images": images,
                        "total": len(tables),
                        "success": success_count,
                        "errors": error_count,
                        "results": results
                    })
                else:
                    console.print(f"\n[green]Completed: {success_count} succeeded, {error_count} failed[/green]")
                    console.print(f"Images mode: {images}")
            else:
                # Single table
                if dry_run:
                    console.print(f"[blue]Dry run - would enable journaling for {library}.{name} with {images}[/blue]")
                    return
                
                result = jrn.enable_journaling(name, library, journal_library, journal_name, images)
                
                if output_json:
                    print_json(console, result)
                else:
                    console.print(f"[green]Enabled journaling for {library}.{name}[/green]")
                    console.print(f"Journal: {result['journal']}")
                    console.print(f"Images: {images}")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("entries")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--limit", default=100, help="Number of entries to retrieve (default: 100)")
@click.option("--format", "output_format", type=click.Choice(["sql", "json"]), default="sql", help="Output format")
@click.pass_context
def journal_entries(
    ctx: click.Context,
    name: str,
    library: str,
    limit: int,
    output_format: str
) -> None:
    """Get journal entries for a table."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            entries = jrn.get_journal_entries(name, library, limit=limit)
            
            if output_format == "json":
                data = [e.model_dump() for e in entries]
                print_json(console, data)
            else:
                # SQL format
                if not entries:
                    console.print("[yellow]No journal entries found for this table.[/yellow]")
                else:
                    for entry in entries:
                        sql = entry.to_sql()
                        if sql:
                            console.print(f"-- Entry {entry.entry_number} ({entry.operation}) at {entry.entry_timestamp}")
                            console.print(f"{sql}\n")
                        else:
                            # Show entry info even if SQL can't be generated
                            console.print(f"-- Entry {entry.entry_number} ({entry.entry_type or 'Unknown'}) at {entry.entry_timestamp}")
                            console.print(f"-- Job: {entry.job_name}, User: {entry.job_user}, Program: {entry.program_name}")
                            if entry.raw_entry_data:
                                console.print(f"-- Raw data: {entry.raw_entry_data[:100]}...\n")
                            else:
                                console.print("-- No data available\n")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("list")
@click.option("--library", "-l", help="Filter by library name")
@click.pass_context
def journal_list(ctx: click.Context, library: str | None) -> None:
    """List all journals with their sizes and status."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.journal import JournalManager
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            if output_json:
                print_json(console, [j.model_dump() for j in journals])
            else:
                if journals:
                    rows = []
                    for j in journals:
                        # Determine size category
                        total_entries = j.get('total_entries', 0) or 0
                        if total_entries < 10000:
                            size_cat = "[green]Small[/green]"
                        elif total_entries < 1000000:
                            size_cat = "[yellow]Medium[/yellow]"
                        else:
                            size_cat = "[red]Large[/red]"
                        
                        rows.append([
                            f"{j['journal_library']}.{j['journal_name']}",
                            str(j.get('receiver_count', 0)),
                            f"{total_entries:,}" if total_entries else "N/A",
                            size_cat,
                            j.get('attached_receiver', 'N/A') or 'N/A'
                        ])
                    
                    console.print(print_table(
                        console,
                        ["Journal", "Receivers", "Total Entries", "Size", "Current Receiver"],
                        rows,
                        title="Journal List"
                    ))
                else:
                    console.print("[yellow]No journals found[/yellow]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("receivers")
@click.option("--journal", "-j", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library name")
@click.pass_context
def journal_receivers(ctx: click.Context, journal: str, library: str) -> None:
    """Show journal receiver chain with cleanup recommendations."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            receivers = jrn.get_receiver_chain(journal, library)
            
            if output_json:
                print_json(console, receivers)
            else:
                if receivers:
                    rows = []
                    for r in receivers:
                        status_icon = "🟢" if r['status'] == 'ATTACHED' else "🔵" if r['status'] == 'ONLINE' else "⚪"
                        cleanup = "[red]KEEP (Attached)[/red]" if r['status'] == 'ATTACHED' else "[green]Safe to cleanup[/green]"
                        rows.append([
                            r['receiver_name'],
                            r['status'],
                            f"{r['entries']:,}" if r['entries'] else "N/A",
                            f"{r['size_mb']:.2f} MB" if r['size_mb'] else "N/A",
                            cleanup
                        ])
                    
                    console.print(print_table(
                        console,
                        ["Receiver", "Status", "Entries", "Size", "Cleanup Status"],
                        rows,
                        title=f"Journal Receivers: {library}.{journal}"
                    ))
                    
                    # Summary
                    total_receivers = len(receivers)
                    attached = sum(1 for r in receivers if r['status'] == 'ATTACHED')
                    online = sum(1 for r in receivers if r['status'] == 'ONLINE')
                    console.print(f"\n[blue]Summary:[/blue] {total_receivers} receivers total ({attached} attached, {online} online, {total_receivers - attached - online} other)")
                    if online > 0:
                        console.print(f"[yellow]Tip:[/yellow] {online} receiver(s) can be saved and deleted to free space")
                else:
                    console.print(f"[yellow]No receivers found for {library}.{journal}[/yellow]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("cleanup")
@click.option("--journal", "-j", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--keep", "-k", default=2, help="Number of recent receivers to keep (default: 2)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without executing")
@click.pass_context
def journal_cleanup(ctx: click.Context, journal: str, library: str, keep: int, dry_run: bool) -> None:
    """Clean up old journal receivers (keeps attached + N recent)."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Get cleanup plan
            plan = jrn.get_cleanup_plan(journal, library, keep)
            
            if not plan['to_delete']:
                console.print(f"[green]No receivers to clean up for {library}.{journal}[/green]")
                return
            
            # Show plan
            console.print(f"\n[blue]Cleanup Plan for {library}.{journal}:[/blue]")
            console.print(f"Keeping: {plan['keeping']} receiver(s)")
            console.print(f"Deleting: {plan['deleting']} receiver(s)")
            console.print(f"Space to free: {plan['space_mb']:.2f} MB\n")
            
            if plan['to_delete']:
                rows = []
                for r in plan['to_delete']:
                    rows.append([r['receiver_name'], f"{r['entries']:,}", f"{r['size_mb']:.2f} MB"])
                console.print(print_table(
                    console,
                    ["Receiver", "Entries", "Size"],
                    rows,
                    title="Receivers to Delete"
                ))
            
            if dry_run:
                console.print(f"\n[yellow]Dry run mode - no changes made[/yellow]")
                console.print(f"Run without --dry-run to execute cleanup")
            else:
                console.print(f"\n[yellow]Executing cleanup...[/yellow]")
                results = jrn.execute_cleanup(plan)
                
                success = sum(1 for r in results if r['success'])
                failed = len(results) - success
                
                console.print(f"[green]Cleanup complete:[/green] {success} deleted, {failed} failed")
                
                if failed > 0:
                    for r in results:
                        if not r['success']:
                            console.print(f"[red]Failed:[/red] {r['receiver_name']} - {r['error']}")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("monitor")
@click.option("--library", "-l", help="Monitor specific library")
@click.option("--threshold", "-t", default=1000000, help="Entry count threshold for warning (default: 1M)")
@click.pass_context
def journal_monitor(ctx: click.Context, library: str | None, threshold: int) -> None:
    """Monitor journal sizes and alert on large journals."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            alerts = []
            rows = []
            
            for j in journals:
                entries = j.get('total_entries', 0) or 0
                
                if entries > threshold * 5:
                    status = "[red]CRITICAL[/red]"
                    alerts.append(f"{j['journal_library']}.{j['journal_name']}: {entries:,} entries")
                elif entries > threshold:
                    status = "[yellow]WARNING[/yellow]"
                    alerts.append(f"{j['journal_library']}.{j['journal_name']}: {entries:,} entries")
                else:
                    status = "[green]OK[/green]"
                
                rows.append([
                    f"{j['journal_library']}.{j['journal_name']}",
                    f"{entries:,}",
                    str(j.get('receiver_count', 0)),
                    status
                ])
            
            if output_json:
                print_json(console, {
                    'journals': journals,
                    'alerts': alerts,
                    'threshold': threshold
                })
            else:
                console.print(print_table(
                    console,
                    ["Journal", "Entries", "Receivers", "Status"],
                    rows,
                    title=f"Journal Monitor (Threshold: {threshold:,} entries)"
                ))
                
                if alerts:
                    console.print(f"\n[yellow]⚠️  Alerts ({len(alerts)}):[/yellow]")
                    for alert in alerts:
                        console.print(f"  • {alert}")
                    console.print(f"\n[blue]Recommendation:[/blue] Use 'journal cleanup' or 'journal receivers' to manage large journals")
                else:
                    console.print(f"\n[green]✓ All journals within threshold[/green]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("info")
@click.option("--name", "-n", required=True, help="Table name (supports wildcards: * or %)")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--fast", "-f", is_flag=True, help="Skip slow entry range query (for large journals)")
@click.pass_context
def journal_info(ctx: click.Context, name: str, library: str, fast: bool) -> None:
    """Get detailed journal information for one or more tables.
    
    Supports wildcards:
      - * or % for multiple characters
      - ? for single character
    
    Examples:
      qadmcli journal info -n TB_01 -l EZPIPE
      qadmcli journal info -n "TB_*" -l EZPIPE --fast
      qadmcli journal info -n "TEST*" -l MYLIB
    """
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Check if wildcard pattern (* and ? are shell-style, % is SQL-style)
            if '*' in name or '%' in name or '?' in name:
                # Find matching tables
                from .db.schema import SchemaManager
                import fnmatch
                schema_mgr = SchemaManager(conn)
                all_tables = schema_mgr.list_tables(library)
                
                # Filter tables by pattern
                pattern = name.replace('%', '*')
                tables = [t for t in all_tables if fnmatch.fnmatch(t.name, pattern)]
                
                if not tables:
                    console.print(f"[yellow]No tables matching pattern '{name}' in {library}[/yellow]")
                    return
                
                # Process each table
                results = []
                console.print(f"[blue]Journal info for {len(tables)} table(s):[/blue]\n")
                
                # Temporarily suppress INFO logging for cleaner batch output
                import logging
                original_level = logging.getLogger("qadmcli").level
                logging.getLogger("qadmcli").setLevel(logging.WARNING)
                
                try:
                    for table in tables:
                        try:
                            info = jrn.get_journal_info(table.name, library, skip_entry_range=fast)
                            results.append({
                                "table": f"{library}.{table.name}",
                                "info": info.model_dump()
                            })
                            
                            # Format journal images for display
                            images_display = info.journal_images or "N/A"
                            if images_display == "*BOTH":
                                images_display = "BOTH"
                            elif images_display == "*AFTER":
                                images_display = "AFTER"
                            elif images_display == "*BEFORE":
                                images_display = "BEFORE"
                            
                            # Compact display for batch mode
                            status = "Journaled" if info.is_journaled else "Not Journaled"
                            journal_info = f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"
                            console.print(f"  {library}.{table.name}: {status} | {images_display} | {journal_info}")
                            
                        except Exception as e:
                            results.append({
                                "table": f"{library}.{table.name}",
                                "error": str(e)
                            })
                            console.print(f"  [red]ERR[/red] {library}.{table.name}: {e}")
                finally:
                    # Restore original logging level
                    logging.getLogger("qadmcli").setLevel(original_level)
                
                if output_json:
                    print_json(console, {
                        "pattern": name,
                        "library": library,
                        "tables": results
                    })
            else:
                # Single table
                info = jrn.get_journal_info(name, library, skip_entry_range=fast)
                
                if output_json:
                    print_json(console, info.model_dump())
                else:
                    # Format journal images for display
                    images_display = info.journal_images or "N/A"
                    if images_display == "*BOTH":
                        images_display = "BOTH (Before & After)"
                    elif images_display == "*AFTER":
                        images_display = "AFTER (After image only)"
                    elif images_display == "*BEFORE":
                        images_display = "BEFORE (Before image only)"
                    
                    content = Text.assemble(
                        ("Table: ", "bold"), f"{library}.{name}", "\n\n",
                        ("Journal Status:\n", "bold underline"),
                        ("  Journaled: ", "bold"), ("Yes" if info.is_journaled else "No"), "\n",
                        ("  Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"), "\n",
                        ("  Write Mode: ", "bold"), images_display, "\n",
                        ("  Receiver: ", "bold"), (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library else "N/A"), "\n",
                        ("  Receiver Attached: ", "bold"), str(info.receiver_attach_timestamp or "N/A"), "\n",
                        ("  Receiver Detached: ", "bold"), str(info.receiver_detach_timestamp or "Still attached"), "\n\n",
                        ("Table Entry Range:\n", "bold underline"),
                        ("  Oldest Sequence: ", "bold"), str(info.oldest_entry_sequence or "N/A"), "\n",
                        ("  Newest Sequence: ", "bold"), str(info.newest_entry_sequence or "N/A"), "\n",
                        ("  Oldest Time: ", "bold"), str(info.oldest_entry_timestamp or "N/A"), "\n",
                        ("  Newest Time: ", "bold"), str(info.newest_entry_timestamp or "N/A"), "\n",
                        ("  Total Entries: ", "bold"), str(info.total_entries or "N/A"),
                    )
                    print_ascii_panel(console, content, title="Detailed Journal Information", border_style="blue")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("create-receiver")
@click.option("--name", "-n", required=True, help="Journal receiver name")
@click.option("--library", "-l", required=True, help="Library for journal receiver")
@click.option("--threshold", "-t", default="*NONE", help="Size threshold (e.g., '100000' or '*NONE')")
@click.pass_context
def journal_create_receiver(
    ctx: click.Context,
    name: str,
    library: str,
    threshold: str
) -> None:
    """Create a standalone journal receiver (not attached to any journal)."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            result = jrn.create_journal_receiver(name, library, threshold)
            
            console.print(f"[green]Created journal receiver {library}.{name}[/green]")
            console.print("[yellow]Note: Receiver is not attached to any journal.[/yellow]")
            console.print("Use 'journal rollover' to attach it to a journal.")
            if threshold != "*NONE":
                console.print(f"Threshold: {threshold} KB")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("rollover")
@click.option("--journal", "-j", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--receiver", "-r", help="New receiver name (auto-generated if not specified)")
@click.option("--receiver-library", "-rl", help="Library for new receiver (defaults to journal library)")
@click.pass_context
def journal_rollover(
    ctx: click.Context,
    journal: str,
    library: str,
    receiver: str | None,
    receiver_library: str | None
) -> None:
    """Rollover journal to a new receiver (detaches current, attaches new).
    
    This creates a new receiver and attaches it to the journal, automatically
    detaching the current receiver. The detached receiver becomes ONLINE status
    and can be cleaned up later.
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            
            # Get current receiver before rollover
            old_receivers = jrn.get_receiver_chain(journal, library)
            old_attached = [r for r in old_receivers if r['status'] == 'ATTACHED']
            old_name = old_attached[0]['receiver_name'] if old_attached else 'Unknown'
            
            # Perform rollover
            result = jrn.rollover_journal(journal, library, receiver, receiver_library)
            
            console.print(f"[green]Journal rollover complete:[/green] {library}.{journal}")
            console.print(f"  Old receiver: {old_name} (now ONLINE)")
            console.print(f"  New receiver: {result['new_receiver']} (now ATTACHED)")
            console.print(f"\n[blue]Tip:[/blue] Use 'journal receivers -j {journal} -l {library}' to view the chain")
            console.print(f"      Use 'journal cleanup -j {journal} -l {library}' to remove old receivers")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("create")
@click.option("--name", "-n", required=True, help="Journal name")
@click.option("--library", "-l", required=True, help="Library for journal")
@click.option("--receiver", "-r", required=True, help="Journal receiver name")
@click.option("--receiver-library", "-rl", help="Journal receiver library (defaults to journal library)")
@click.option("--msg-queue", "-m", default="*NONE", help="Message queue for journal messages")
@click.pass_context
def journal_create(
    ctx: click.Context,
    name: str,
    library: str,
    receiver: str,
    receiver_library: str | None,
    msg_queue: str
) -> None:
    """Create a journal."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            result = jrn.create_journal(name, library, receiver, receiver_library, msg_queue)
            
            recv_lib = receiver_library or library
            console.print(f"[green]Created journal {library}.{name}[/green]")
            console.print(f"Attached to receiver: {recv_lib}.{receiver}")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.group()
def user() -> None:
    """User management commands."""
    pass


@user.command("check")
@click.option("--user", "-u", required=True, help="Username to check")
@click.option("--library", "-l", help="Library to check permissions on")
@click.option("--name", "-n", help="Table name(s) to check (supports wildcards like 'customer*')")
@click.pass_context
def user_check(
    ctx: click.Context,
    user: str,
    library: str | None,
    name: str | None
) -> None:
    """Check user existence and permissions."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            result = user_mgr.check_user(user, library, name)
            
            if output_json:
                print_json(console, result)
            else:
                if result["exists"]:
                    user_class = str(result.get("user_class", "N/A"))
                    status = str(result.get("status", "N/A"))
                    
                    # Build user info content for ASCII panel
                    user_info_content = f"""User: {user}
Exists: Yes
User Class: {user_class}
Status: {status}"""
                    
                    print_ascii_panel(
                        console,
                        user_info_content,
                        title="User Information",
                        border_style="green"
                    )
                    
                    if result.get("permissions"):
                        rows = []
                        for perm in result["permissions"]:
                            rows.append([
                                perm.get("object", ""),
                                perm.get("object_type", ""),
                                perm.get("authority", "")
                            ])
                        console.print(print_table(
                            console,
                            ["Object", "Type", "Authority"],
                            rows,
                            title="Table Permissions"
                        ))
                    
                    # Display journal permissions
                    if result.get("journal_permissions"):
                        rows = []
                        for perm in result["journal_permissions"]:
                            rows.append([
                                perm.get("object", ""),
                                perm.get("object_type", ""),
                                perm.get("authority", "")
                            ])
                        console.print(print_table(
                            console,
                            ["Object", "Type", "Authority"],
                            rows,
                            title="Journal Permissions"
                        ))
                    elif library:
                        console.print("[yellow]No journal permissions found in library {library}.[/yellow]".format(library=library))
                else:
                    console.print(f"[yellow]User {user} does not exist.[/yellow]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("check-table")
@click.option("--user", "-u", required=True, help="Username to check")
@click.option("--name", "-n", required=True, help="Table name to check")
@click.option("--library", "-l", required=True, help="Library containing the table")
@click.pass_context
def user_check_table(
    ctx: click.Context,
    user: str,
    name: str,
    library: str
) -> None:
    """Check user permissions for a specific table and its related journal objects.
    
    Shows a consolidated view of permissions on:
    - The table itself
    - The journal (even if in different library)
    - The journal receiver
    """
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            result = user_mgr.check_table_permissions_with_journal(user, name, library)
            
            if output_json:
                print_json(console, result)
            else:
                # Build consolidated view
                print_ascii_panel(
                    console,
                    f"Checking permissions for {user} on {library}.{name}",
                    title="Table Permission Check",
                    border_style="blue"
                )
                
                # Display user info (group profile and special authorities)
                user_info_lines = []
                if result["user_info"]["group_profile"] and result["user_info"]["group_profile"] != "*NONE":
                    user_info_lines.append(["Group Profile", result["user_info"]["group_profile"]])
                if result["user_info"]["special_authorities"] and result["user_info"]["special_authorities"] != "*NONE":
                    user_info_lines.append(["Special Authorities", result["user_info"]["special_authorities"]])
                
                if user_info_lines:
                    console.print(print_table(
                        console,
                        ["Attribute", "Value"],
                        user_info_lines,
                        title="User Information"
                    ))
                
                # Helper function to format authority details
                def format_auth_details(details: list) -> str:
                    if not details:
                        return "No explicit authority found"
                    lines = []
                    for d in details:
                        auth = d["authority"]
                        source = d["source"]
                        lines.append(f"  - {source}: {auth}")
                    return "\n".join(lines)
                
                # Table info with authority sources
                table_auth = result["table"]["authority"] or "*NONE"
                table_source = result["table"]["source"] or "N/A"
                table_details = format_auth_details(result["table"]["details"])
                
                table_rows = [
                    ["Object", f"{result['table']['library']}.{result['table']['name']}"],
                    ["Type", "*FILE"],
                    ["Effective Authority", table_auth],
                    ["Primary Source", table_source],
                    ["Authority Details", table_details]
                ]
                console.print(print_table(
                    console,
                    ["Property", "Value"],
                    table_rows,
                    title="Table Permissions"
                ))
                
                # Journal info (if table is journaled)
                if result["journal"]["name"]:
                    jrn_auth = result["journal"]["authority"] or "*NONE"
                    jrn_source = result["journal"]["source"] or "N/A"
                    jrn_details = format_auth_details(result["journal"]["details"])
                    
                    jrn_rows = [
                        ["Object", f"{result['journal']['library']}.{result['journal']['name']}"],
                        ["Type", "*JRN"],
                        ["Effective Authority", jrn_auth],
                        ["Primary Source", jrn_source],
                        ["Authority Details", jrn_details]
                    ]
                    console.print(print_table(
                        console,
                        ["Property", "Value"],
                        jrn_rows,
                        title="Journal Permissions"
                    ))
                    
                    # Journal receiver info
                    if result["journal_receiver"]["name"]:
                        rcv_auth = result["journal_receiver"]["authority"] or "*NONE"
                        rcv_source = result["journal_receiver"]["source"] or "N/A"
                        rcv_details = format_auth_details(result["journal_receiver"]["details"])
                        
                        rcv_rows = [
                            ["Object", f"{result['journal_receiver']['library']}.{result['journal_receiver']['name']}"],
                            ["Type", "*JRNRCV"],
                            ["Effective Authority", rcv_auth],
                            ["Primary Source", rcv_source],
                            ["Authority Details", rcv_details]
                        ]
                        console.print(print_table(
                            console,
                            ["Property", "Value"],
                            rcv_rows,
                            title="Journal Receiver Permissions"
                        ))
                    
                    # Summary
                    all_auths = [table_auth, jrn_auth, rcv_auth]
                    if all(a in ["*ALL", "*CHANGE"] for a in all_auths):
                        console.print("[green]User has full permissions on table and journal objects.[/green]")
                    elif "*NONE" in all_auths or None in all_auths:
                        console.print("[yellow]Warning: User may have insufficient permissions on some objects.[/yellow]")
                else:
                    console.print("[yellow]Table is not journaled.[/yellow]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("create")
@click.option("--user", "-u", required=True, help="Username to create")
@click.option("--password", "-p", help="Password for the user")
@click.option("--library", "-l", help="Library to grant permissions on")
@click.option("--name", "-n", help="Table name(s) to grant permissions (supports wildcards)")
@click.pass_context
def user_create(
    ctx: click.Context,
    user: str,
    password: str | None,
    library: str | None,
    name: str | None
) -> None:
    """Create a new user with optional permissions."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            result = user_mgr.create_user(user, password)
            console.print(f"[green]Created user {user}[/green]")
            
            if library:
                # Grant permissions on library/tables
                user_mgr.grant_library_permissions(user, library, name)
                console.print(f"[green]Granted permissions on {library}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("delete")
@click.option("--user", "-u", required=True, help="Username to delete")
@click.option("--force", "-f", is_flag=True, help="Force delete without confirmation")
@click.pass_context
def user_delete(
    ctx: click.Context,
    user: str,
    force: bool
) -> None:
    """Delete a user."""
    config_path = ctx.obj["config_path"]
    
    if not force:
        console.print(f"[yellow]Warning: This will permanently delete user {user}[/yellow]")
        console.print("Use --force to confirm.")
        sys.exit(1)
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            user_mgr.delete_user(user)
            console.print(f"[green]Deleted user {user}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("grant")
@click.option("--user", "-u", required=True, help="Username to grant permissions to")
@click.option("--grant", "-g", "grant_option", required=True, 
              type=click.Choice(["*ALL", "*CHANGE", "*USE", "*EXCLUDE", "*ALLOBJ", "*SECADM", 
                                "*JOBCTL", "*SPLCTL", "*SAVSYS", "*SERVICE", "*AUDIT", "*IOSYSCFG"]),
              help="Authority to grant")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--name", "-n", help="Object name(s) (supports wildcards like 'customer*')")
@click.option("--object-type", "-t", default="*FILE",
              type=click.Choice(["*FILE", "*JRN", "*JRNRCV", "*LIB", "*ALL"]),
              help="Object type (default: *FILE)")
@click.pass_context
def user_grant(
    ctx: click.Context,
    user: str,
    grant_option: str,
    library: str,
    name: str | None,
    object_type: str
) -> None:
    """Grant authority to a user on library/objects.
    
    Common authority options:
    - *ALL: All authority
    - *CHANGE: Read and modify authority
    - *USE: Use authority (read/execute)
    - *EXCLUDE: No authority
    - *ALLOBJ: All object authority (special)
    
    Object types:
    - *FILE: Database files (tables)
    - *JRN: Journals
    - *JRNRCV: Journal receivers
    - *LIB: Libraries
    - *ALL: All object types
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            object_name = name.upper() if name else "*ALL"
            user_mgr.grant_object_authority(user, library, object_name, grant_option, object_type)
            
            console.print(f"[green]Granted {grant_option} authority to {user}[/green]")
            console.print(f"Object: {library}.{object_name} ({object_type})")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("password")
@click.option("--user", "-u", required=True, help="Username")
@click.option("--password", "-p", required=True, help="New password")
@click.pass_context
def user_password(
    ctx: click.Context,
    user: str,
    password: str
) -> None:
    """Reset user password."""
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            user_mgr.change_password(user, password)
            console.print(f"[green]Password changed for user {user}[/green]")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@user.command("permission")
@click.option("--user", "-u", required=True, help="Username")
@click.option("--library", "-l", help="Filter by library")
@click.pass_context
def user_permission(
    ctx: click.Context,
    user: str,
    library: str | None
) -> None:
    """List user permissions and authority."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            result = user_mgr.list_permissions(user, library)
            
            if output_json:
                print_json(console, result)
            else:
                console.print(Panel(
                    Text.assemble(
                        ("User: ", "bold"), user, "\n",
                        ("User Class: ", "bold"), result.get("user_class", "N/A"), "\n",
                        ("Group Profile: ", "bold"), result.get("group_profile", "None"), "\n",
                        ("Special Authorities: ", "bold"), ", ".join(result.get("special_authorities", [])), "\n",
                    ),
                    title="User Permissions",
                    border_style="blue"
                ))
                
                if result.get("object_authorities"):
                    rows = []
                    for auth in result["object_authorities"]:
                        rows.append([
                            auth.get("library", ""),
                            auth.get("object", ""),
                            auth.get("object_type", ""),
                            auth.get("authority", "")
                        ])
                    console.print(print_table(
                        console,
                        ["Library", "Object", "Type", "Authority"],
                        rows,
                        title="Object Authorities"
                    ))
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.group()
def library() -> None:
    """Library management commands."""
    pass


@library.command("create")
@click.option("--name", "-n", required=True, help="Library name to create")
@click.option("--user", "-u", help="User to grant authority to (optional)")
@click.option("--authority", "-a", default="*ALL", help="Authority level to grant (*USE, *CHANGE, *ALL)")
@click.pass_context
def library_create(
    ctx: click.Context,
    name: str,
    user: str | None,
    authority: str
) -> None:
    """Create a new library and optionally grant user authority.
    
    Examples:
        qadmcli library create -n NEWLIB
        qadmcli library create -n NEWLIB -u USER001
        qadmcli library create -n NEWLIB -u USER001 -a *CHANGE
    """
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            # Create the library
            result = user_mgr.create_library(name)
            
            # Grant authority if user specified
            if user:
                grant_result = user_mgr.grant_object_authority(
                    user, name, name, authority, "*LIB"
                )
                result["granted_to"] = user
                result["authority"] = authority
            
            if output_json:
                print_json(console, result)
            else:
                print_ascii_panel(
                    console,
                    f"Library {name} created successfully",
                    title="Library Created",
                    border_style="green"
                )
                if user:
                    console.print(f"Granted {authority} authority to {user}")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@library.command("grant")
@click.option("--name", "-n", required=True, help="Library name")
@click.option("--user", "-u", required=True, help="User to grant authority to")
@click.option("--authority", "-a", default="*USE", help="Authority level (*USE, *CHANGE, *ALL)")
@click.pass_context
def library_grant(
    ctx: click.Context,
    name: str,
    user: str,
    authority: str
) -> None:
    """Grant authority to a user on a library.
    
    Examples:
        qadmcli library grant -n MYLIB -u USER001
        qadmcli library grant -n MYLIB -u USER001 -a *ALL
    """
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from .db.user import UserManager
            user_mgr = UserManager(conn)
            
            result = user_mgr.grant_object_authority(
                user, name, name, authority, "*LIB"
            )
            
            if output_json:
                print_json(console, result)
            else:
                print_ascii_panel(
                    console,
                    f"Granted {authority} authority to {user} on library {name}",
                    title="Authority Granted",
                    border_style="green"
                )
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.group()
def mockup() -> None:
    """Mockup data generation commands."""
    pass


def _load_schema_hints(schema_path: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Load column hints and validation rules from a YAML schema file.

    Returns a tuple of (hints dict, validation dict).
    """
    import yaml
    import re

    hints = {}
    validation = {}
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = yaml.safe_load(f)

        if schema and 'columns' in schema:
            for col in schema['columns']:
                col_name = col.get('name')
                description = col.get('description', '')

                # Extract hint from description
                if col_name and description:
                    hint_match = re.search(r'\[hint:([^\]]+)\]', description, re.IGNORECASE)
                    if hint_match:
                        hints[col_name.upper()] = hint_match.group(1).strip()

                # Build validation rules for this column
                if col_name:
                    validation[col_name.upper()] = {
                        'type': col.get('type'),
                        'length': col.get('length'),
                        'scale': col.get('scale'),
                        'nullable': col.get('nullable'),
                    }

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load schema from {schema_path}: {e}[/yellow]")

    return hints, validation


@mockup.command("generate")
@click.option("--name", "-n", required=True, help="Table name (e.g., TB_02)")
@click.option("--library", "-l", required=True, help="Library/schema name (e.g., EZPIPE)")
@click.option("--schema", "-s", help="Schema YAML file for column hints and validation")
@click.option("--skip-validation", is_flag=True, help="Skip schema validation when using --schema")
@click.option("--transactions", "-t", default=1000, show_default=True, help="Total number of transactions to generate")
@click.option("--insert-ratio", default=50, show_default=True, help="Percentage of INSERT operations (0-100)")
@click.option("--update-ratio", default=30, show_default=True, help="Percentage of UPDATE operations (0-100)")
@click.option("--delete-ratio", default=20, show_default=True, help="Percentage of DELETE operations (0-100)")
@click.option("--batch-size", "-b", default=100, show_default=True, help="Number of operations per batch commit")
@click.option("--dry-run", is_flag=True, help="Preview SQL statements without executing")
@click.pass_context
def mockup_generate(
    ctx: click.Context,
    name: str,
    library: str,
    schema: Optional[str],
    skip_validation: bool,
    transactions: int,
    insert_ratio: int,
    update_ratio: int,
    delete_ratio: int,
    batch_size: int,
    dry_run: bool
) -> None:
    """Generate mock data with INSERT/UPDATE/DELETE operations.

    Generates realistic test data by automatically detecting field patterns based on column names.
    Supports tables with single or composite primary keys.

    \b
    Field Patterns (auto-detected):
        - first_name: FIRST_NAME, FNAME, FIRSTNAME
        - last_name: LAST_NAME, LNAME, LASTNAME, SURNAME
        - email: EMAIL, E_MAIL, MAIL
        - phone: PHONE, MOBILE, TEL, CELL
        - date: DATE, CREATED_DATE, UPDATED_DATE
        - amount: AMOUNT, PRICE, COST, FEE, TAX
        - id: ID, CUST_ID, USER_ID, ORDER_ID
        - status: STATUS, TYPE, ORDER_STATUS
        - string: CHAR, VARCHAR (default fallback)

    \b
    Examples:
        # Dry run - preview SQL without executing
        qadmcli mockup generate -n TB_02 -l EZPIPE --dry-run -t 10

        # Generate 1000 transactions with default ratios (50% insert, 30% update, 20% delete)
        qadmcli mockup generate -n CUSTOMERS -l MYLIB -t 1000

        # Custom transaction mix - 60% inserts, 30% updates, 10% deletes
        qadmcli mockup generate -n ORDERS -l MYLIB -t 500 \\
            --insert-ratio 60 --update-ratio 30 --delete-ratio 10

        # Use schema file for custom column hints
        qadmcli mockup generate -n PRODUCTS -l MYLIB -s config/schema/products.yaml -t 100

    \b
    Notes:
        - Ratios must sum to exactly 100
        - Table must have a primary key for UPDATE/DELETE operations
        - Composite primary keys are supported
        - Large tables (millions of rows) are handled efficiently using sampling
    """
    config_path = ctx.obj["config_path"]

    # Validate ratios
    total_ratio = insert_ratio + update_ratio + delete_ratio
    if total_ratio != 100:
        console.print(f"[red]Error: Ratios must sum to 100, got {total_ratio}[/red]")
        sys.exit(1)

    try:
        from .db.mockup import MockupManager, MockupConfig, SchemaValidationError

        config = load_config(config_path)

        mockup_config = MockupConfig(
            insert_ratio=insert_ratio,
            update_ratio=update_ratio,
            delete_ratio=delete_ratio,
            total_transactions=transactions,
            batch_size=batch_size,
            dry_run=dry_run
        )

        # Load schema hints and validation if provided
        schema_hints = {}
        schema_validation = {}
        if schema:
            schema_hints, schema_validation = _load_schema_hints(schema)
            console.print(f"[blue]Loaded hints from schema: {schema}[/blue]")
            if skip_validation:
                console.print(f"[yellow]Schema validation skipped[/yellow]")
                schema_validation = {}  # Clear validation rules

        with AS400ConnectionManager(config) as conn:
            mock_mgr = MockupManager(conn, schema_hints, schema_validation)

            console.print(f"[blue]Generating mock data for {library}.{name}...[/blue]")
            console.print(f"  Transactions: {transactions} (Insert: {insert_ratio}%, Update: {update_ratio}%, Delete: {delete_ratio}%)")
            console.print(f"  Batch size: {batch_size}")
            if dry_run:
                console.print(f"  [yellow]Dry run mode - generating SQL only[/yellow]")

            results = mock_mgr.generate_mock_data(name, library, mockup_config)
            
            if dry_run:
                # Output SQL statements
                sql_count = len(results["sql_statements"])
                console.print(f"\n[green]Generated {sql_count} SQL statements:[/green]")
                
                # Show first 10 statements
                for i, sql in enumerate(results["sql_statements"][:10]):
                    console.print(sql)
                
                if sql_count > 10:
                    console.print(f"\n... and {sql_count - 10} more statements")
            else:
                # Show statistics
                stats = results["stats"]
                console.print(f"\n[green]Mock data generation complete:[/green]")
                console.print(f"  Inserted: {stats['inserted']} rows")
                console.print(f"  Updated: {stats['updated']} rows")
                console.print(f"  Deleted: {stats['deleted']} rows")

    except SchemaValidationError as e:
        console.print(f"[red]Schema validation error:[/red]")
        console.print(f"[yellow]{e}[/yellow]")
        console.print(f"\n[blue]Tip: Use --dry-run to preview without validation, or fix the table schema to match.[/blue]")
        sys.exit(1)
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.group()
def sql() -> None:
    """SQL execution commands."""
    pass


@sql.command("execute")
@click.option("--query", "-q", required=True, help="SQL query to execute")
@click.pass_context
def sql_execute(ctx: click.Context, query: str) -> None:
    """Execute a SQL query and display results."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            cursor = conn.execute(query)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch all rows
            rows = cursor.fetchall()
            cursor.close()
            
            if output_json:
                # Convert to list of dicts for JSON output
                results = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[str(col)] = row[i]
                    results.append(row_dict)
                print_json(console, results)
            else:
                # Format as table
                if rows:
                    table_rows = []
                    for row in rows:
                        table_rows.append([str(cell) if cell is not None else "NULL" for cell in row])
                    
                    # Sanitize column names for Windows terminal compatibility
                    # Replace non-ASCII characters that may render as Thai characters
                    def sanitize_column(name: str) -> str:
                        """Sanitize column name for Windows terminal display."""
                        # Replace common problematic characters
                        sanitized = str(name)
                        # Replace ellipsis and other Unicode characters with ASCII equivalents
                        replacements = {
                            '\u2026': '...',  # Horizontal ellipsis
                            '\u2018': "'",    # Left single quote
                            '\u2019': "'",    # Right single quote
                            '\u201C': '"',    # Left double quote
                            '\u201D': '"',    # Right double quote
                            '\u2013': '-',    # En dash
                            '\u2014': '--',   # Em dash
                        }
                        for unicode_char, ascii_char in replacements.items():
                            sanitized = sanitized.replace(unicode_char, ascii_char)
                        # Truncate if too long (prevents wrapping issues)
                        if len(sanitized) > 30:
                            sanitized = sanitized[:27] + '...'
                        return sanitized
                    
                    str_columns = [sanitize_column(str(col)) for col in columns]
                    console.print(print_table(
                        console,
                        str_columns,
                        table_rows,
                        title="Query Results"
                    ))
                    console.print(f"[green]{len(rows)} row(s) returned[/green]")
                else:
                    console.print("[yellow]No rows returned[/yellow]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
