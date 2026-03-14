"""QADM CLI - Main entry point."""

import os
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from . import __version__
from .config import load_config
from .db.connection import AS400ConnectionManager, ConnectionError
from .db.schema import SchemaManager
from .db.journal import JournalManager
from .models.table import TableConfig
from .utils.logger import setup_logging
from .utils.formatters import print_table, print_json

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
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            schema = SchemaManager(conn)
            exists = schema.table_exists(name, library)
            
            if exists:
                info = schema.get_table_info(name, library)
                if output_json:
                    print_json(console, info.model_dump() if info else {})
                else:
                    console.print(Panel(
                        Text.assemble(
                            ("Table: ", "bold"), f"{library}.{name}", "\n",
                            ("Exists: ", "bold"), ("Yes", "green"), "\n",
                            ("Type: ", "bold"), info.table_type if info else "N/A", "\n",
                            ("Rows: ", "bold"), str(info.row_count) if info and info.row_count else "N/A", "\n",
                            ("Journaled: ", "bold"), ("Yes", "green") if info and info.journaled else ("No", "yellow"), "\n",
                            ("Created: ", "bold"), info.created if info else "N/A",
                        ),
                        title="Table Information",
                        border_style="green"
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
                    rows = [[t.name, t.table_type, str(t.row_count or 0), "Yes" if t.journaled else "No"] for t in tables]
                    console.print(print_table(
                        console,
                        ["Table Name", "Type", "Rows", "Journaled"],
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


@journal.command("enable")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.option("--journal-library", "-j", help="Journal library (default from config)")
@click.option("--journal-name", help="Journal name (default: QSQJRN)")
@click.pass_context
def journal_enable(
    ctx: click.Context,
    name: str,
    library: str,
    journal_library: str | None,
    journal_name: str | None
) -> None:
    """Enable journaling for a table."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            result = jrn.enable_journaling(name, library, journal_library, journal_name)
            
            if output_json:
                print_json(console, result)
            else:
                console.print(f"[green]Enabled journaling for {library}.{name}[/green]")
                console.print(f"Journal: {result['journal']}")
        
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
                for entry in entries:
                    sql = entry.to_sql()
                    if sql:
                        console.print(f"-- Entry {entry.entry_number} ({entry.operation}) at {entry.entry_timestamp}")
                        console.print(f"{sql}\n")
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@journal.command("info")
@click.option("--name", "-n", required=True, help="Table name")
@click.option("--library", "-l", required=True, help="Library name")
@click.pass_context
def journal_info(ctx: click.Context, name: str, library: str) -> None:
    """Get detailed journal information for a table."""
    config_path = ctx.obj["config_path"]
    output_json = ctx.obj["output_json"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            info = jrn.get_journal_info(name, library)
            
            if output_json:
                print_json(console, info.model_dump())
            else:
                console.print(Panel(
                    Text.assemble(
                        ("Table: ", "bold"), f"{library}.{name}", "\n\n",
                        ("Journal Status:\n", "bold underline"),
                        ("  Journaled: ", "bold"), ("Yes" if info.is_journaled else "No"), "\n",
                        ("  Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library else "N/A"), "\n",
                        ("  Receiver: ", "bold"), (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library else "N/A"), "\n\n",
                        ("Entry Range:\n", "bold underline"),
                        ("  Oldest Sequence: ", "bold"), str(info.oldest_entry_sequence or "N/A"), "\n",
                        ("  Newest Sequence: ", "bold"), str(info.newest_entry_sequence or "N/A"), "\n",
                        ("  Oldest Time: ", "bold"), str(info.oldest_entry_timestamp or "N/A"), "\n",
                        ("  Newest Time: ", "bold"), str(info.newest_entry_timestamp or "N/A"), "\n",
                        ("  Total Entries: ", "bold"), str(info.total_entries or "N/A"),
                    ),
                    title="Detailed Journal Information",
                    border_style="blue"
                ))
        
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
