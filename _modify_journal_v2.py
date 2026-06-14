#!/usr/bin/env python3
"""Apply agent delegation to journal_commands.py - readonly commands"""
import sys

# Workaround for triple-quote escaping issues: read template from external file
# Instead, we directly generate the target source using single-line builds

with open("src/qadmcli/cli_commands/journal_commands.py") as f:
    content = f.read()

# ============================================================
# 1. Add EPOCH_START and _dt_to_dotnet_ticks after print_panel import
# ============================================================
old_import = (
    "from ..utils.formatters import print_table, print_json_clean\n"
    "from .utils import print_panel"
)
new_import = (
    "from ..utils.formatters import print_table, print_json_clean\n"
    "from .utils import print_panel\n"
    "\n"
    "EPOCH_START = datetime(1, 1, 1)\n"
    "\n"
    "\n"
    "def _dt_to_dotnet_ticks(dt: datetime) -> int:\n"
    '    """Convert Python datetime to .NET ticks (100-nanosecond intervals since 0001-01-01)."""\n'
    "    return int((dt - EPOCH_START).total_seconds() * 10_000_000)\n"
)
assert old_import in content, "Missing print_panel import!"
content = content.replace(old_import, new_import, 1)

# ============================================================
# 2. journal check - add agent delegation
# ============================================================
# Find the existing try block inside journal_check
old_check = (
    "    try:\n"
    "        config = load_config(config_path)\n"
    "        \n"
    "        with AS400ConnectionManager(config) as conn:\n"
    "            jrn = JournalManager(conn)\n"
    "            info = jrn.get_journal_info(table, library)\n"
    "            \n"
    "            if output_format == \"json\":\n"
    "                print_json_clean(info.get_summary())\n"
    "            else:\n"
    "                status_color = \"green\" if info.is_journaled else \"yellow\"\n"
    "                print_panel(\n"
    "                    ctx,\n"
    "                    Text.assemble(\n"
    '                        ("Table: ", "bold"), f"{library}.{table}", "\\n",\n'
    '                        ("Journaled: ", "bold"), ("Yes" if info.is_journaled else "No", status_color), "\\n",\n'
    '                        ("Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library and info.journal_name else "N/A"), "\\n",\n'
    '                        ("Receiver: ", "bold"), \n'
    '                        (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library and info.journal_receiver_name else "N/A"), "\\n",\n'
    '                        ("Entry Range: ", "bold"), \n'
    '                        (f"{info.oldest_entry_sequence} - {info.newest_entry_sequence}" if info.oldest_entry_sequence and info.newest_entry_sequence else "N/A"),\n'
    "                    ),\n"
    '                    title="Journal Information",\n'
    "                    border_style=status_color\n"
    "                )\n"
    "        \n"
    "    except ConnectionError as e:\n"
    '        console.print(f"[red]Connection error: {e.message}[/red]")\n'
    "        sys.exit(1)\n"
    "    except Exception as e:\n"
    '        console.print(f"[red]Error: {e}[/red]")\n'
    "        sys.exit(1)"
)

new_check = """    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                # Query JOURNALED_OBJECTS - check if table is journaled
                check_result = client.query(
                    "SELECT JOURNAL_LIBRARY, JOURNAL_NAME, JOURNAL_IMAGES "
                    "FROM QSYS2.JOURNALED_OBJECTS "
                    "WHERE (OBJECT_NAME = ? OR OBJECT_NAME = ?) "
                    "AND OBJECT_LIBRARY = ? AND OBJECT_TYPE = '*FILE'",
                    params=[table.upper(), table.upper(), library.upper()]
                )
                is_journaled = check_result["row_count"] > 0
                j_lib = j_name = j_images = r_lib = r_name = None
                if is_journaled:
                    row = check_result["rows"][0]
                    j_lib = row[0] or None
                    j_name = row[1] or None
                    j_images = row[2] or None
                    # Get receiver info
                    if j_lib and j_name:
                        recv_result = client.query(
                            "SELECT ATTACHED_JOURNAL_RECEIVER_LIBRARY, "
                            "ATTACHED_JOURNAL_RECEIVER_NAME "
                            "FROM QSYS2.JOURNAL_INFO "
                            "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?",
                            params=[j_lib, j_name]
                        )
                        if recv_result["row_count"] > 0:
                            r_lib = recv_result["rows"][0][0] or None
                            r_name = recv_result["rows"][0][1] or None
                
                if output_format == "json":
                    from ..utils.formatters import print_json_clean
                    print_json_clean({
                        "table": f"{library}.{table}",
                        "is_journaled": is_journaled,
                        "journal_library": j_lib,
                        "journal_name": j_name,
                        "journal_images": j_images,
                        "journal_receiver_library": r_lib,
                        "journal_receiver_name": r_name,
                    })
                else:
                    status_color = "green" if is_journaled else "yellow"
                    journal_str = f"{j_lib}.{j_name}" if j_lib and j_name else "N/A"
                    receiver_str = f"{r_lib}.{r_name}" if r_lib and r_name else "N/A"
                    print_panel(
                        ctx,
                        Text.assemble(
                            ("Table: ", "bold"), f"{library}.{table}", "\\n",
                            ("Journaled: ", "bold"), ("Yes" if is_journaled else "No", status_color), "\\n",
                            ("Journal: ", "bold"), (journal_str, status_color), "\\n",
                            ("Receiver: ", "bold"), (receiver_str, status_color), "\\n",
                        ),
                        title="Journal Information",
                        border_style=status_color
                    )
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            info = jrn.get_journal_info(table, library)
            
            if output_format == "json":
                print_json_clean(info.get_summary())
            else:
                status_color = "green" if info.is_journaled else "yellow"
                print_panel(
                    ctx,
                    Text.assemble(
                        ("Table: ", "bold"), f"{library}.{table}", "\\n",
                        ("Journaled: ", "bold"), ("Yes" if info.is_journaled else "No", status_color), "\\n",
                        ("Journal: ", "bold"), (f"{info.journal_library}.{info.journal_name}" if info.journal_library and info.journal_name else "N/A"), "\\n",
                        ("Receiver: ", "bold"), 
                        (f"{info.journal_receiver_library}.{info.journal_receiver_name}" if info.journal_receiver_library and info.journal_receiver_name else "N/A"), "\\n",
                        ("Entry Range: ", "bold"), 
                        (f"{info.oldest_entry_sequence} - {info.newest_entry_sequence}" if info.oldest_entry_sequence and info.newest_entry_sequence else "N/A"),
                    ),
                    title="Journal Information",
                    border_style=status_color
                )
        
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)"""

assert old_check in content, "journal_check try block not found!"
content = content.replace(old_check, new_check)

# ============================================================
# 3. journal list - add agent delegation
# ============================================================
old_list = (
    'def journal_list(ctx: click.Context, library: str | None, output_format: str) -> None:\n'
    '    """List all journals with their sizes and status."""\n'
    '    config_path = ctx.obj["config_path"]\n'
    '    \n'
    '    try:\n'
    '        config = load_config(config_path)\n'
    '        \n'
    '        with AS400ConnectionManager(config) as conn:\n'
    '            from ..db.journal import JournalManager\n'
    '            jrn = JournalManager(conn)\n'
    '            journals = jrn.list_journals(library)\n'
    '            \n'
    '            if output_format == "json":\n'
    '                print_json_clean([j.model_dump() for j in journals])\n'
    '            else:\n'
    '                if journals:\n'
    '                    rows = []\n'
    '                    for j in journals:\n'
    '                        # Determine size category\n'
    "                        total_entries = j.get('total_entries', 0) or 0\n"
    '                        if total_entries < 10000:\n'
    '                            size_cat = "[green]Small[/green]"\n'
    '                        elif total_entries < 1000000:\n'
    '                            size_cat = "[yellow]Medium[/yellow]"\n'
    '                        else:\n'
    '                            size_cat = "[red]Large[/red]"\n'
    '                        \n'
    "                        rows.append([\n"
    "                            f\"{j['journal_library']}.{j['journal_name']}\",\n"
    "                            str(j.get('receiver_count', 0)),\n"
    '                            f"{total_entries:,}" if total_entries else "N/A",\n'
    '                            size_cat,\n'
    "                            j.get('attached_receiver', 'N/A') or 'N/A'\n"
    '                        ])\n'
    '                    \n'
    '                    console.print(print_table(\n'
    '                        console,\n'
    '                        ["Journal", "Receivers", "Total Entries", "Size", "Current Receiver"],\n'
    '                        rows,\n'
    '                        title="Journal List"\n'
    '                    ))\n'
    '                else:\n'
    '                    console.print("[yellow]No journals found[/yellow]")\n'
    '    \n'
    '    except ConnectionError as e:\n'
    '        console.print(f"[red]Connection error: {e.message}[/red]")\n'
    '        sys.exit(1)\n'
    '    except Exception as e:\n'
    '        console.print(f"[red]Error: {e}[/red]")\n'
    '        sys.exit(1)'
)

new_list = '''def journal_list(ctx: click.Context, library: str | None, output_format: str) -> None:
    """List all journals with their sizes and status."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                sql = (
                    "SELECT JOURNAL_LIBRARY, JOURNAL_NAME, "
                    "COUNT(*) as RECEIVER_COUNT, "
                    "SUM(NUMBER_OF_JOURNAL_ENTRIES) as TOTAL_ENTRIES, "
                    "MAX(CASE WHEN STATUS = 'ATTACHED' THEN JOURNAL_RECEIVER_NAME END) as ATTACHED_RECEIVER "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE 1=1"
                )
                params = []
                if library:
                    sql += " AND JOURNAL_LIBRARY = ?"
                    params.append(library.upper())
                sql += " GROUP BY JOURNAL_LIBRARY, JOURNAL_NAME ORDER BY TOTAL_ENTRIES DESC"
                
                result = client.query(sql, params=params if params else None)
                rows_data = result.get("rows", [])
                
                if output_format == "json":
                    journals = []
                    for row in rows_data:
                        journals.append({
                            "journal_library": row[0] or "",
                            "journal_name": row[1] or "",
                            "receiver_count": row[2] or 0,
                            "total_entries": row[3] or 0,
                            "attached_receiver": row[4] or None
                        })
                    from ..utils.formatters import print_json_clean
                    print_json_clean(journals)
                else:
                    if rows_data:
                        table_rows = []
                        for row in rows_data:
                            j_lib = row[0] or ""
                            j_name = row[1] or ""
                            recv_count = row[2] or 0
                            total_entries = row[3] or 0
                            attached_recv = row[4] or "N/A"
                            
                            if total_entries < 10000:
                                size_cat = "[green]Small[/green]"
                            elif total_entries < 1000000:
                                size_cat = "[yellow]Medium[/yellow]"
                            else:
                                size_cat = "[red]Large[/red]"
                            
                            table_rows.append([
                                f"{j_lib}.{j_name}",
                                str(recv_count),
                                f"{total_entries:,}" if total_entries else "N/A",
                                size_cat,
                                attached_recv
                            ])
                        
                        from ..utils.formatters import print_table
                        console.print(print_table(
                            console,
                            ["Journal", "Receivers", "Total Entries", "Size", "Current Receiver"],
                            table_rows,
                            title="Journal List"
                        ))
                    else:
                        console.print("[yellow]No journals found[/yellow]")
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            from ..db.journal import JournalManager
            jrn = JournalManager(conn)
            journals = jrn.list_journals(library)
            
            if output_format == "json":
                print_json_clean(journals)
            else:
                if journals:
                    rows = []
                    for j in journals:
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
        sys.exit(1)'''

assert old_list in content, "journal_list function not found!"
content = content.replace(old_list, new_list)

# ============================================================
# 4. journal receivers - add agent delegation
# ============================================================
old_recv = (
    'def journal_receivers(ctx: click.Context, journal: str, library: str, output_format: str) -> None:\n'
    '    """Show journal receiver chain with cleanup recommendations."""\n'
    '    config_path = ctx.obj["config_path"]\n'
    '    \n'
    '    try:\n'
    '        config = load_config(config_path)\n'
    '        \n'
    '        with AS400ConnectionManager(config) as conn:\n'
    '            jrn = JournalManager(conn)\n'
    '            receivers = jrn.get_receiver_chain(journal, library)\n'
    '            \n'
    '            if output_format == "json":\n'
    '                print_json_clean(receivers)\n'
    '            else:\n'
    '                if receivers:\n'
    '                    rows = []\n'
    '                    for r in receivers:\n'
    "                        status_icon = \"\U0001f7e2\" if r['status'] == 'ATTACHED' else \"\U0001f535\" if r['status'] == 'ONLINE' else \"\u26aa\"\n"
    '                        cleanup = "[red]KEEP (Attached)[/red]" if r[\'status\'] == \'ATTACHED\' else "[green]Safe to cleanup[/green]"\n'
    '                        rows.append([\n'
    "                            r['receiver_name'],\n"
    "                            r['status'],\n"
    '                            f"{r[\'entries\']:,}" if r[\'entries\'] else "N/A",\n'
    '                            f"{r[\'size_mb\']:.2f} MB" if r[\'size_mb\'] else "N/A",\n'
    '                            cleanup\n'
    '                        ])\n'
    '                    \n'
    '                    console.print(print_table(\n'
    '                        console,\n'
    '                        ["Receiver", "Status", "Entries", "Size", "Cleanup Status"],\n'
    '                        rows,\n'
    '                        title=f"Journal Receivers: {library}.{journal}"\n'
    '                    ))\n'
    '                    \n'
    '                    # Summary\n'
    "                    total_receivers = len(receivers)\n"
    "                    attached = sum(1 for r in receivers if r['status'] == 'ATTACHED')\n"
    "                    online = sum(1 for r in receivers if r['status'] == 'ONLINE')\n"
    '                    console.print(f"\\n[blue]Summary:[/blue] {total_receivers} receivers total ({attached} attached, {online} online, {total_receivers - attached - online} other)")\n'
    '                    if online > 0:\n'
    '                        console.print(f"[yellow]Tip:[/yellow] {online} receiver(s) can be saved and deleted to free space")\n'
    '                else:\n'
    '                    console.print(f"[yellow]No receivers found for {library}.{journal}[/yellow]")\n'
    '    \n'
    '    except ConnectionError as e:\n'
    '        console.print(f"[red]Connection error: {e.message}[/red]")\n'
    '        sys.exit(1)\n'
    '    except Exception as e:\n'
    '        console.print(f"[red]Error: {e}[/red]")\n'
    '        sys.exit(1)'
)

new_recv = '''def journal_receivers(ctx: click.Context, journal: str, library: str, output_format: str) -> None:
    """Show journal receiver chain with cleanup recommendations."""
    config_path = ctx.obj["config_path"]
    
    try:
        # Check if agent is available (no JVM needed in CLI)
        agent_url = os.environ.get("QADMCLI_AGENT_URL")
        if agent_url:
            from ..db.agent_client import AS400AgentClient
            client = AS400AgentClient(agent_url)
            if client.is_available():
                result = client.query(
                    "SELECT JOURNAL_RECEIVER_LIBRARY, JOURNAL_RECEIVER_NAME, "
                    "NUMBER_OF_JOURNAL_ENTRIES, STATUS, SIZE "
                    "FROM QSYS2.JOURNAL_RECEIVER_INFO "
                    "WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ? "
                    "ORDER BY CASE STATUS "
                    "WHEN 'ATTACHED' THEN 1 WHEN 'ONLINE' THEN 2 ELSE 3 END, "
                    "JOURNAL_RECEIVER_NAME",
                    params=[library.upper(), journal.upper()]
                )
                rows_data = result.get("rows", [])
                
                if output_format == "json":
                    receivers = []
                    for row in rows_data:
                        size_bytes = row[4] or 0
                        size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
                        receivers.append({
                            "receiver_library": row[0] or "",
                            "receiver_name": row[1] or "",
                            "entries": row[2] or 0,
                            "status": row[3] or "UNKNOWN",
                            "size_mb": round(size_mb, 2)
                        })
                    from ..utils.formatters import print_json_clean
                    print_json_clean(receivers)
                else:
                    if rows_data:
                        receiver_list = []
                        for row in rows_data:
                            r_name = row[1] or ""
                            r_status = row[3] or "UNKNOWN"
                            r_entries = row[2] or 0
                            size_bytes = row[4] or 0
                            size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
                            
                            cleanup = "[red]KEEP (Attached)[/red]" if r_status == 'ATTACHED' else "[green]Safe to cleanup[/green]"
                            receiver_list.append({
                                "name": r_name,
                                "status": r_status,
                                "entries": r_entries,
                                "size_mb": size_mb,
                                "cleanup_label": cleanup
                            })
                        
                        if receiver_list:
                            table_rows = []
                            for r in receiver_list:
                                table_rows.append([
                                    r["name"],
                                    r["status"],
                                    f"{r['entries']:,}" if r["entries"] else "N/A",
                                    f"{r['size_mb']:.2f} MB" if r["size_mb"] else "N/A",
                                    r["cleanup_label"]
                                ])
                            
                            from ..utils.formatters import print_table
                            console.print(print_table(
                                console,
                                ["Receiver", "Status", "Entries", "Size", "Cleanup Status"],
                                table_rows,
                                title=f"Journal Receivers: {library}.{journal}"
                            ))
                            
                            total_receivers = len(receiver_list)
                            attached = sum(1 for r in receiver_list if r["status"] == 'ATTACHED')
                            online = sum(1 for r in receiver_list if r["status"] == 'ONLINE')
                            console.print(f"\\n[blue]Summary:[/blue] {total_receivers} receivers total ({attached} attached, {online} online, {total_receivers - attached - online} other)")
                            if online > 0:
                                console.print(f"[yellow]Tip:[/yellow] {online} receiver(s) can be saved and deleted to free space")
                    else:
                        console.print(f"[yellow]No receivers found for {library}.{journal}[/yellow]")
                return
        
        config = load_config(config_path)
        
        with AS400ConnectionManager(config) as conn:
            jrn = JournalManager(conn)
            receivers = jrn.get_receiver_chain(journal, library)
            
            if output_format == "json":
                print_json_clean(receivers)
            else:
                if receivers:
                    rows = []
                    for r in receivers:
                        status_icon = "\\U0001f7e2" if r['status'] == 'ATTACHED' else "\\U0001f535" if r['status'] == 'ONLINE' else "\\u26aa"
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
                    console.print(f"\\n[blue]Summary:[/blue] {total_receivers} receivers total ({attached} attached, {online} online, {total_receivers - attached - online} other)")
                    if online > 0:
                        console.print(f"[yellow]Tip:[/yellow] {online} receiver(s) can be saved and deleted to free space")
                else:
                    console.print(f"[yellow]No receivers found for {library}.{journal}[/yellow]")
    
    except ConnectionError as e:
        console.print(f"[red]Connection error: {e.message}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)'''

assert old_recv in content, "journal_receivers function not found!"
content = content.replace(old_recv, new_recv)

# ============================================================
# Write result
# ============================================================
with open("src/qadmcli/cli_commands/journal_commands.py", "w") as f:
    f.write(content)

print(f"Done. File size: {len(content)} chars, {content.count(chr(10))} lines")

# Verify syntax
import ast
try:
    ast.parse(content)
    print("SYNTAX: OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR: {e}")
    sys.exit(1)
