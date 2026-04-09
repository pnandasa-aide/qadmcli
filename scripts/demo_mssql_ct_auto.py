#!/usr/bin/env python3
"""
Automated MSSQL Change Tracking Demo

This script demonstrates the full CT workflow by:
1. Creating a demo table
2. Enabling CT on database and table
3. Inserting/updating/deleting data
4. Querying changes at each step

Usage:
    python demo_mssql_ct_auto.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from qadmcli.config import load_config
from qadmcli.db.mssql import MSSQLConnection
from qadmcli.db.mssql_ct import MSSQLChangeTracking
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

DEMO_TABLE = "CT_DEMO_CUSTOMERS"
DEMO_SCHEMA = "dbo"


def print_header(title: str):
    """Print a formatted header."""
    console.print(f"\n[bold cyan]{'=' * 60}[/bold cyan]")
    console.print(f"[bold cyan]  {title}[/bold cyan]")
    console.print(f"[bold cyan]{'=' * 60}[/bold cyan]")


def print_step(number: int, description: str):
    """Print a step header."""
    console.print(f"\n[bold yellow][Step {number}] {description}[/bold yellow]")


def demo_ct_workflow():
    """Run the complete CT demo workflow."""
    print_header("MSSQL Change Tracking - Automated Demo")
    
    # Load configuration
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'connection.yaml')
    config = load_config(config_path)
    
    if not config.mssql:
        console.print("[red]Error: MSSQL configuration not found[/red]")
        sys.exit(1)
    
    console.print(f"\n[dim]Connecting to MSSQL: {config.mssql.host}:{config.mssql.port}[/dim]")
    
    with MSSQLConnection(config.mssql) as conn:
        ct = MSSQLChangeTracking(conn)
        
        # Step 1: Check current status
        print_step(1, "Checking current CT status")
        status = ct.get_table_ct_status(DEMO_TABLE, DEMO_SCHEMA)
        console.print(f"Database: {status.database_name}")
        console.print(f"CT on Database: {'[green]Yes[/green]' if status.is_enabled_on_database else '[red]No[/red]'}")
        console.print(f"CT on Table: {'[green]Yes[/green]' if status.is_enabled_on_table else '[red]No[/red]'}")
        
        # Step 2: Enable CT on database if needed
        if not status.is_enabled_on_database:
            print_step(2, "Enabling CT on database")
            try:
                ct.enable_database_ct(retention_days=2, auto_cleanup=True)
                console.print("[green]CT enabled on database successfully![/green]")
            except Exception as e:
                console.print(f"[red]Error enabling CT on database: {e}[/red]")
                console.print("[yellow]This may require admin privileges. Use -U/-P options.[/yellow]")
                return
        else:
            console.print("[dim]CT already enabled on database[/dim]")
        
        # Step 3: Create demo table
        print_step(3, f"Creating demo table: {DEMO_SCHEMA}.{DEMO_TABLE}")
        try:
            with conn.get_cursor() as cursor:
                # Drop if exists
                cursor.execute(f"""
                    IF OBJECT_ID('{DEMO_SCHEMA}.{DEMO_TABLE}', 'U') IS NOT NULL
                        DROP TABLE {DEMO_SCHEMA}.{DEMO_TABLE}
                """)
                
                # Create table
                cursor.execute(f"""
                    CREATE TABLE {DEMO_SCHEMA}.{DEMO_TABLE} (
                        CUST_ID INT IDENTITY(1000, 1) PRIMARY KEY,
                        FIRST_NAME NVARCHAR(50) NOT NULL,
                        LAST_NAME NVARCHAR(50) NOT NULL,
                        EMAIL NVARCHAR(100),
                        STATUS NVARCHAR(20) DEFAULT 'ACTIVE',
                        CREATED_AT DATETIME2 DEFAULT GETDATE(),
                        UPDATED_AT DATETIME2 DEFAULT GETDATE()
                    )
                """)
                console.print("[green]Demo table created successfully![/green]")
        except Exception as e:
            console.print(f"[red]Error creating table: {e}[/red]")
            return
        
        # Step 4: Enable CT on table
        print_step(4, f"Enabling CT on table {DEMO_SCHEMA}.{DEMO_TABLE}")
        try:
            ct.enable_table_ct(DEMO_TABLE, DEMO_SCHEMA, track_columns_updated=True)
            console.print("[green]CT enabled on table successfully![/green]")
        except Exception as e:
            console.print(f"[red]Error enabling CT on table: {e}[/red]")
            return
        
        # Step 5: Insert test data
        print_step(5, "Inserting test data (generates 'I' operations)")
        with conn.get_cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO {DEMO_SCHEMA}.{DEMO_TABLE} (FIRST_NAME, LAST_NAME, EMAIL, STATUS)
                VALUES 
                    ('John', 'Doe', 'john.doe@example.com', 'ACTIVE'),
                    ('Jane', 'Smith', 'jane.smith@example.com', 'ACTIVE'),
                    ('Bob', 'Johnson', 'bob.j@example.com', 'PENDING'),
                    ('Alice', 'Williams', 'alice.w@example.com', 'ACTIVE'),
                    ('Charlie', 'Brown', 'charlie.b@example.com', 'ACTIVE')
            """)
            console.print("[green]Inserted 5 records[/green]")
        
        # Step 6: Query changes (should show 'I' operations)
        print_step(6, "Querying changes (expecting 'I' - Insert operations)")
        changes = ct.get_changes(DEMO_TABLE, DEMO_SCHEMA, since_version=0)
        display_changes(changes)
        
        # Step 7: Update data
        print_step(7, "Updating data (generates 'U' operations)")
        with conn.get_cursor() as cursor:
            cursor.execute(f"""
                UPDATE {DEMO_SCHEMA}.{DEMO_TABLE} 
                SET STATUS = 'INACTIVE', 
                    UPDATED_AT = GETDATE(),
                    EMAIL = 'john.doe.updated@example.com'
                WHERE CUST_ID = 1000
            """)
            cursor.execute(f"""
                UPDATE {DEMO_SCHEMA}.{DEMO_TABLE} 
                SET STATUS = 'ACTIVE',
                    UPDATED_AT = GETDATE()
                WHERE CUST_ID = 1002
            """)
            console.print("[green]Updated 2 records[/green]")
        
        # Step 8: Query changes again (should show 'I' and 'U')
        print_step(8, "Querying changes again (expecting 'I' and 'U' operations)")
        changes = ct.get_changes(DEMO_TABLE, DEMO_SCHEMA, since_version=0)
        display_changes(changes)
        
        # Step 9: Delete data
        print_step(9, "Deleting data (generates 'D' operations)")
        with conn.get_cursor() as cursor:
            cursor.execute(f"DELETE FROM {DEMO_SCHEMA}.{DEMO_TABLE} WHERE CUST_ID = 1004")
            console.print("[green]Deleted 1 record[/green]")
        
        # Step 10: Query final changes (should show 'I', 'U', 'D')
        print_step(10, "Querying final changes (expecting 'I', 'U', and 'D' operations)")
        changes = ct.get_changes(DEMO_TABLE, DEMO_SCHEMA, since_version=0)
        display_changes(changes)
        
        # Summary
        print_header("Demo Complete!")
        
        # Count operations
        op_counts = {}
        for change in changes:
            op = change.sys_change_operation
            op_counts[op] = op_counts.get(op, 0) + 1
        
        summary_table = Table(title="Operation Summary")
        summary_table.add_column("Operation", style="cyan")
        summary_table.add_column("Count", style="green")
        summary_table.add_column("Description", style="dim")
        
        op_descriptions = {
            'I': 'Insert (new records)',
            'U': 'Update (modified records)',
            'D': 'Delete (removed records)'
        }
        
        for op, count in sorted(op_counts.items()):
            summary_table.add_row(op, str(count), op_descriptions.get(op, ''))
        
        console.print(summary_table)
        
        # Cleanup
        console.print("\n[yellow]Cleanup: Disabling CT on demo table...[/yellow]")
        try:
            ct.disable_table_ct(DEMO_TABLE, DEMO_SCHEMA)
            console.print("[green]CT disabled on table[/green]")
            
            with conn.get_cursor() as cursor:
                cursor.execute(f"DROP TABLE {DEMO_SCHEMA}.{DEMO_TABLE}")
            console.print("[green]Demo table dropped[/green]")
        except Exception as e:
            console.print(f"[yellow]Cleanup warning: {e}[/yellow]")
        
        console.print("\n[bold green]Demo completed successfully![/bold green]")


def display_changes(changes):
    """Display changes in a formatted table."""
    if not changes:
        console.print("[yellow]No changes found[/yellow]")
        return
    
    table = Table(title=f"Change Tracking Changes ({len(changes)} total)")
    table.add_column("Version", style="cyan")
    table.add_column("Operation", style="yellow")
    table.add_column("PK Values", style="green")
    table.add_column("Context", style="dim")
    
    op_colors = {
        'I': 'green',
        'U': 'yellow',
        'D': 'red'
    }
    
    for change in changes:
        op = change.sys_change_operation
        op_display = f"[{op_colors.get(op, 'white')}]{op}[/{op_colors.get(op, 'white')}]")
        pk_str = ", ".join(f"{k}={v}" for k, v in change.primary_key_values.items())
        
        table.add_row(
            str(change.sys_change_version),
            op_display,
            pk_str,
            change.sys_change_context or ""
        )
    
    console.print(table)


if __name__ == "__main__":
    try:
        demo_ct_workflow()
    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Demo failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)
