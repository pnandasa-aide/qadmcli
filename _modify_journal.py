#!/usr/bin/env python3
"""Apply agent delegation to journal_commands.py"""

import re

with open("src/qadmcli/cli_commands/journal_commands.py") as f:
    content = f.read()

# 1. Add EPOCH_START and _dt_to_dotnet_ticks after print_panel import
old = "from ..utils.formatters import print_table, print_json_clean\nfrom .utils import print_panel"
new = """from ..utils.formatters import print_table, print_json_clean
from .utils import print_panel

EPOCH_START = datetime(1, 1, 1)


def _dt_to_dotnet_ticks(dt: datetime) -> int:
    \"\"\"Convert Python datetime to .NET ticks (100-nanosecond intervals since 0001-01-01).\"\"\"
    return int((dt - EPOCH_START).total_seconds() * 10_000_000)"""

assert old in content, "print_panel import not found!"
content = content.replace(old, new, 1)

# 2. journal check - add agent delegation
old = """    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            info = jrn.get_journal_info(table, library)
            
            if output_format == \"json\":
                print_json_clean(info.get_summary())
            else:
                status_color = \"green\" if info.is_journaled else \"yellow\"
                print_panel(
                    ctx,
                    Text.assemble(
                        (\"Table: \", \"bold\"), f\"{library}.{table}\", \"\\n\",
                        (\"Journaled: \", \"bold\"), (\"Yes\" if info.is_journaled else \"No\", status_color), \"\\n\",
                        (\"Journal: \", \"bold\"), (f\"{info.journal_library}.{info.journal_name}\" if info.journal_library and info.journal_name else \"N/A\"), \"\\n\",
                        (\"Receiver: \", \"bold\"), 
                        (f\"{info.journal_receiver_library}.{info.journal_receiver_name}\" if info.journal_receiver_library and info.journal_receiver_name else \"N/A\"), \"\\n\",
                        (\"Entry Range: \", \"bold\"), 
                        (f\"{info.oldest_entry_sequence} - {info.newest_entry_sequence}\" if info.oldest_entry_sequence and info.newest_entry_sequence else \"N/A\"),
                    ),
                    title=\"Journal Information\",
                    border_style=status_color
                )"""

# Needs unique context - include the function def start
old2_start = """def journal_check(ctx: click.Context, table: str, library: str, output_format: str) -> None:
    \"\"\"Check journal status for a table.\"\"\"
    config_path = ctx.obj[\"config_path\"]
    
    # Suppress logging for JSON output
    if output_format == \"json\":
        import logging
        logging.getLogger(\"qadmcli\").setLevel(logging.WARNING)
    
    try:"""

assert old2_start in content, "journal_check not found!"

# Build the replacement - agent delegation + JT400 fallback (only try/except block)
new2 = """def journal_check(ctx: click.Context, table: str, library: str, output_format: str) -> None:
    \"\"\"Check journal status for a table.\"\"\"
    config_path = ctx.obj[\"config_path\"]
    
    # Suppress logging for JSON output
    if output_format == \"json\":
        import logging
        logging.getLogger(\"qadmcli\").setLevel(logging.WARNING)
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get(\"QADMCLI_AGENT_URL\")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                # Query JOURNALED_OBJECTS
                check_result = client.query(
                    \"SELECT JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES \"\"
                    \"FROM QSYS2.JOURNALED_OBJECTS \"\"
                    \"WHERE (OBJECT_NAME = ? OR OBJECT_NAME = ?) \"\"
                    \"AND OBJECT_LIBRARY = ? AND OBJECT_TYPE = '*FILE'\",
                    params=[table.upper(), table.upper(), library.upper()]
                )
                is_journaled = check_result[\"row_count\"] > 0
                j_lib = j_name = j_images = r_lib = r_name = None
                if is_journaled:
                    row = check_result[\"rows\"][0]
                    j_lib = row[0] or None
                    j_name = row[1] or None
                    j_images = row[2] or None
                    # Get receiver info
                    if j_lib and j_name:
                        recv_result = client.query(
                            \"SELECT ATTACHED_JOURNAL_RECEIVER_LIBRARY, \"\"
                            \"ATTACHED_JOURNAL_RECEIVER_NAME \"\"
                            \"FROM QSYS2.JOURNAL_INFO \"\"
                            \"WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?\",
                            params=[j_lib, j_name]
                        )
                        if recv_result[\"row_count\"] > 0:
                            r_lib = recv_result[\"rows\"][0][0] or None
                            r_name = recv_result[\"rows\"][0][1] or None
                
                if output_format == \"json\":
                    from ..utils.formatters import print_json_clean
                    print_json_clean({
                        \"table\": f\"{library}.{table}\",
                        \"is_journaled\": is_journaled,
                        \"journal_library\": j_lib,
                        \"journal_name\": j_name,
                        \"journal_images\": j_images,
                        \"journal_receiver_library\": r_lib,
                        \"journal_receiver_name\": r_name,
                    })
                else:
                    status_color = \"green\" if is_journaled else \"yellow\"
                    journal_str = f\"{j_lib}.{j_name}\" if j_lib and j_name else \"N/A\"
                    receiver_str = f\"{r_lib}.{r_name}\" if r_lib and r_name else \"N/A\"
                    print_panel(
                        ctx,
                        Text.assemble(
                            (\"Table: \", \"bold\"), f\"{library}.{table}\", \"\\n\",
                            (\"Journaled: \", \"bold\"), (\"Yes\" if is_journaled else \"No\", status_color), \"\\n\",
                            (\"Journal: \", \"bold\"), (journal_str, status_color), \"\\n\",
                            (\"Receiver: \", \"bold\"), (receiver_str, status_color), \"\\n\",
                        ),
                        title=\"Journal Information\",
                        border_style=status_color
                    )
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            info = jrn.get_journal_info(table, library)
            
            if output_format == \"json\":
                print_json_clean(info.get_summary())
            else:
                status_color = \"green\" if info.is_journaled else \"yellow\"
                print_panel(
                    ctx,
                    Text.assemble(
                        (\"Table: \", \"bold\"), f\"{library}.{table}\", \"\\n\",
                        (\"Journaled: \", \"bold\"), (\"Yes\" if info.is_journaled else \"No\", status_color), \"\\n\",
                        (\"Journal: \", \"bold\"), (f\"{info.journal_library}.{info.journal_name}\" if info.journal_library and info.journal_name else \"N/A\"), \"\\n\",
                        (\"Receiver: \", \"bold\"), 
                        (f\"{info.journal_receiver_library}.{info.journal_receiver_name}\" if info.journal_receiver_library and info.journal_receiver_name else \"N/A\"), \"\\n\",
                        (\"Entry Range: \", \"bold\"), 
                        (f\"{info.oldest_entry_sequence} - {info.newest_entry_sequence}\" if info.oldest_entry_sequence and info.newest_entry_sequence else \"N/A\"),
                    ),
                    title=\"Journal Information\",
                    border_style=status_color
                )"""

content = content.replace(old2_start, new2, 1)

# 3. journal list - add agent delegation
old3 = """def journal_list(ctx: click.Context, library: str | None, output_format: str) -> None:
    \"\"\"List all journals with their sizes and status.\"\"\"
    config_path = ctx.obj[\"config_path\"]
    
    try:
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from ..db.journal import JournalManager
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            if output_format == \"json\":
                print_json_clean([j.model_dump() for j in journals])
            else:
                if journals:
                    rows = []
                    for j in journals:
                        # Determine size category
                        total_entries = j.get('total_entries', 0) or 0
                        if total_entries < 10000:
                            size_cat = \"[green]Small[/green]\"
                        elif total_entries < 1000000:
                            size_cat = \"[yellow]Medium[/yellow]\"
                        else:
                            size_cat = \"[red]Large[/red]\"
                        
                        rows.append([
                            f\"{j['journal_library']}.{j['journal_name']}\",
                            str(j.get('receiver_count', 0)),
                            f\"{total_entries:,}\" if total_entries else \"N/A\",
                            size_cat,
                            j.get('attached_receiver', 'N/A') or 'N/A'
                        ])
                    
                    console.print(print_table(
                        console,
                        [\"Journal\", \"Receivers\", \"Total Entries\", \"Size\", \"Current Receiver\"],
                        rows,
                        title=\"Journal List\"
                    ))
                else:
                    console.print(\"[yellow]No journals found[/yellow]\")
    """

new3 = """def journal_list(ctx: click.Context, library: str | None, output_format: str) -> None:
    \"\"\"List all journals with their sizes and status.\"\"\"
    config_path = ctx.obj[\"config_path\"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get(\"QADMCLI_AGENT_URL\")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                sql = (
                    \"SELECT JOURNAL_LIBRARY, JOURNAL_NAME, \"\"
                    \"COUNT(*) as RECEIVER_COUNT, \"\"
                    \"SUM(NUMBER_OF_JOURNAL_ENTRIES) as TOTAL_ENTRIES, \"\"
                    \"MAX(CASE WHEN STATUS = 'ATTACHED' THEN JOURNAL_RECEIVER_NAME END) as ATTACHED_RECEIVER \"\"
                    \"FROM QSYS2.JOURNAL_RECEIVER_INFO \"\"
                    \"WHERE 1=1\"
                )
                params = []
                if library:
                    sql += \" AND JOURNAL_LIBRARY = ?\"
                    params.append(library.upper())
                sql += \" GROUP BY JOURNAL_LIBRARY, JOURNAL_NAME ORDER BY TOTAL_ENTRIES DESC\"
                
                result = client.query(sql, params=params if params else None)
                rows_data = result.get(\"rows\", [])
                
                if output_format == \"json\":
                    journals = []
                    for row in rows_data:
                        journals.append({
                            \"journal_library\": row[0] or \"\",
                            \"journal_name\": row[1] or \"\",
                            \"receiver_count\": row[2] or 0,
                            \"total_entries\": row[3] or 0,
                            \"attached_receiver\": row[4] or None
                        })
                    from ..utils.formatters import print_json_clean
                    print_json_clean(journals)
                else:
                    if rows_data:
                        table_rows = []
                        for row in rows_data:
                            j_lib = row[0] or \"\"
                            j_name = row[1] or \"\"
                            recv_count = row[2] or 0
                            total_entries = row[3] or 0
                            attached_recv = row[4] or \"N/A\"
                            
                            if total_entries < 10000:
                                size_cat = \"[green]Small[/green]\"
                            elif total_entries < 1000000:
                                size_cat = \"[yellow]Medium[/yellow]\"
                            else:
                                size_cat = \"[red]Large[/red]\"
                            
                            table_rows.append([
                                f\"{j_lib}.{j_name}\",
                                str(recv_count),
                                f\"{total_entries:,}\" if total_entries else \"N/A\",
                                size_cat,
                                attached_recv
                            ])
                        
                        from ..utils.formatters import print_table
                        console.print(print_table(
                            console,
                            [\"Journal\", \"Receivers\", \"Total Entries\", \"Size\", \"Current Receiver\"],
                            table_rows,
                            title=\"Journal List\"
                        ))
                    else:
                        console.print(\"[yellow]No journals found[/yellow]\")
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from ..db.journal import JournalManager
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            if output_format == \"json\":
                print_json_clean(journals)
            else:
                if journals:
                    rows = []
                    for j in journals:
                        total_entries = j.get('total_entries', 0) or 0
                        if total_entries < 10000:
                            size_cat = \"[green]Small[/green]\"
                        elif total_entries < 1000000:
                            size_cat = \"[yellow]Medium[/yellow]\"
                        else:
                            size_cat = \"[red]Large[/red]\"
                        
                        rows.append([
                            f\"{j['journal_library']}.{j['journal_name']}\",
                            str(j.get('receiver_count', 0)),
                            f\"{total_entries:,}\" if total_entries else \"N/A\",
                            size_cat,
                            j.get('attached_receiver', 'N/A') or 'N/A'
                        ])
                    
                    console.print(print_table(
                        console,
                        [\"Journal\", \"Receivers\", \"Total Entries\", \"Size\", \"Current Receiver\"],
                        rows,
                        title=\"Journal List\"
                    ))
                else:
                    console.print(\"[yellow]No journals found[/yellow]\")
    """

assert old3 in content, "journal_list not found!"
content = content.replace(old3, new3, 1)

# Write result
with open("src/qadmcli/cli_commands/journal_commands.py", "w") as f:
    f.write(content)

print("✅ journal_commands.py updated successfully")
print(f"New file size: {len(content)} chars, {content.count(chr(10))} lines")
