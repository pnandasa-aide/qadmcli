"""Output formatters."""

import json
from typing import Any

from rich.console import Console
from rich.table import Table as RichTable
from rich.json import JSON as RichJSON


def format_table(
    headers: list[str],
    rows: list[list[Any]],
    title: str | None = None
) -> RichTable:
    """Format data as Rich table."""
    table = RichTable(title=title, show_header=True, header_style="bold magenta")
    
    for header in headers:
        table.add_column(header)
    
    for row in rows:
        table.add_row(*[str(cell) for cell in row])
    
    return table


def format_json(data: Any, indent: int = 2) -> str:
    """Format data as JSON string."""
    return json.dumps(data, indent=indent, default=str, ensure_ascii=False)


def print_table(
    console: Console,
    headers: list[str],
    rows: list[list[Any]],
    title: str | None = None
) -> None:
    """Print formatted table to console."""
    table = format_table(headers, rows, title)
    console.print(table)


def print_json(console: Console, data: Any, indent: int = 2) -> None:
    """Print formatted JSON to console."""
    json_str = format_json(data, indent)
    console.print(RichJSON(json_str))
