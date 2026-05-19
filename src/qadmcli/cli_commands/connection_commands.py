"""Connection Commands Module.

This module contains connection-related CLI commands:
- connection test-as400: Test AS400 DB2 connection
- connection test-mssql: Test MSSQL connection
"""

import sys

import click
from rich.console import Console

from ..config import load_config
from ..db.connection import AS400ConnectionManager, ConnectionError
from ..db.mssql import MSSQLConnection
from ..utils.formatters import print_json_clean
from .utils import print_panel

console = Console()


@click.group()
def connection():
    """Connection management commands."""
    pass


@connection.command("test-as400")
@click.option("-U", "--username", help="Test connection with specific username (admin user)")
@click.option("-P", "--password", help="Password for the specified username")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def connection_test_as400(ctx: click.Context, username: str | None, password: str | None, output_format: str) -> None:
    """Test connection to AS400 DB2 for i.
    
    Examples:
        qadmcli connection test-as400
        qadmcli connection test-as400 -U ADMIN -P password
        qadmcli connection test-as400 --format json
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        # Override credentials if provided
        if username:
            config.as400.user = username
        if password:
            config.as400.password = password
        
        with AS400ConnectionManager(config) as conn:
            info = conn.test_connection()
        
            if output_format == "json":
                print_json_clean(info)
            else:
                print_panel(
                    ctx,
                    f"Host: {info.get('host', 'N/A')}\n"
                    f"Port: {info.get('port', 'N/A')}\n"
                    f"User: {info.get('user', 'N/A')}\n"
                    f"Database: {info.get('database', 'N/A')}\n"
                    f"Status: [green]Connected[/green]",
                    title="Connection Test Result",
                    border_style="green"
                )
        
    except ConnectionError as e:
        if output_format == "json":
            print_json_clean({"error": str(e), "status": "failed"})
        else:
            console.print(f"[red]Connection failed: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        if output_format == "json":
            print_json_clean({"error": str(e), "status": "failed"})
        else:
            console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@connection.command("test-mssql")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format (default: table)")
@click.pass_context
def connection_test_mssql(ctx: click.Context, output_format: str) -> None:
    """Test connection to MSSQL Server.
    
    Examples:
        qadmcli connection test-mssql
        qadmcli connection test-mssql --format json
    """
    config_path = ctx.obj["config_path"]
    
    try:
        config = load_config(config_path)
        
        # Check if MSSQL config exists
        if not hasattr(config, 'mssql') or not config.mssql:
            console.print("[red]Error: No MSSQL configuration found in config file[/red]")
            console.print("[dim]Please add MSSQL connection details to your connection.yaml[/dim]")
            sys.exit(1)
        
        mssql_config = config.mssql
        
        # Create MSSQL connection (MSSQLConnection expects MSSQLConnection model)
        mssql = MSSQLConnection(mssql_config)
        
        # Test connection
        mssql.connect()
        try:
            # Execute simple query to verify connection
            with mssql.get_cursor() as cursor:
                cursor.execute("SELECT @@VERSION AS version, DB_NAME() AS database_name")
                result = cursor.fetchone()
                
                if result:
                    version_info = result.version or 'Unknown'
                    db_name = result.database_name or 'Unknown'
                    
                    # Extract MSSQL version (first line)
                    version_short = version_info.split('\n')[0] if version_info else 'Unknown'
                    
                    if output_format == "json":
                        print_json_clean({
                            "status": "connected",
                            "host": mssql_config.host,
                            "port": mssql_config.port,
                            "database": db_name,
                            "user": mssql_config.username,
                            "version": version_short
                        })
                    else:
                        print_panel(
                            ctx,
                            f"Host: {mssql_config.host}\n"
                            f"Port: {mssql_config.port}\n"
                            f"Database: {db_name}\n"
                            f"User: {mssql_config.username}\n"
                            f"Version: {version_short}\n"
                            f"Status: [green]Connected[/green]",
                            title="MSSQL Connection Test Result",
                            border_style="green"
                        )
                else:
                    console.print("[red]Connection test failed - no results returned[/red]")
                    sys.exit(1)
        finally:
            mssql.disconnect()
        
    except Exception as e:
        if output_format == "json":
            print_json_clean({"error": str(e), "status": "failed"})
        else:
            console.print(f"[red]Connection failed: {e}[/red]")
        sys.exit(1)


def register_connection_commands(cli_group):
    """Register connection commands with the main CLI group."""
    cli_group.add_command(connection)
