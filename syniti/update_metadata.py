#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import sys
import os
import argparse
from datetime import datetime, timezone

def datetime_to_ticks(dt_str):
    """
    Converts an ISO/common datetime string to .NET Ticks.
    Supported formats:
    - 2026-06-03 08:03:15.326656
    - 2026-06-03T08:03:15
    - Raw integer (returns as string if it looks like ticks already)
    """
    dt_str = dt_str.strip()
    if dt_str.isdigit():
        return dt_str
        
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(dt_str, fmt)
            # Use UTC timestamp conversion
            utc_timestamp = dt.replace(tzinfo=timezone.utc).timestamp()
            ticks = int((utc_timestamp + 62135596800) * 10000000)
            return str(ticks)
        except ValueError:
            continue
            
    raise ValueError(f"Could not parse datetime: {dt_str}. Use YYYY-MM-DD HH:MM:SS.ffffff or raw ticks.")

def main():
    parser = argparse.ArgumentParser(
        description="Update Syniti metadata XML with specific sequence numbers, timestamps, libraries, and journals."
    )
    parser.add_argument(
        "-m", "--xml",
        default="/home/ubuntu/_qoder/qadmcli/syniti/Metadata_deves_1.xml",
        help="Path to the Syniti metadata XML file (default: Metadata_deves_1.xml)"
    )
    parser.add_argument(
        "-s", "--seq",
        help="Target replication TransactionID / Sequence Number (e.g. 100627)"
    )
    parser.add_argument(
        "-t", "--ts",
        help="Target replication TransactionTS / Timestamp (e.g. '2026-06-03 08:03:15.326656' or raw .NET ticks)"
    )
    parser.add_argument(
        "--src-lib",
        default="SYNITI",
        help="Source library/schema to replace (default: SYNITI)"
    )
    parser.add_argument(
        "--trg-lib",
        default="TBLIBTST",
        help="Target library/schema to replace with (default: TBLIBTST)"
    )
    parser.add_argument(
        "--src-jrn",
        default="DSJRN",
        help="Source journal name to replace (default: DSJRN)"
    )
    parser.add_argument(
        "--trg-jrn",
        default="QSQJRN",
        help="Target journal name to replace with (default: QSQJRN)"
    )
    parser.add_argument(
        "--src-rcv",
        default="DSJRNRCV",
        help="Source receiver name to replace (default: DSJRNRCV)"
    )
    parser.add_argument(
        "--trg-rcv",
        default="QSQJRN",
        help="Target receiver name to replace with (default: QSQJRN)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.xml):
        print(f"Error: XML file not found at {args.xml}")
        sys.exit(1)

    print(f"Reading metadata from {args.xml}...")
    tree = ET.parse(args.xml)
    root = tree.getroot()

    # Determine sequence and timestamp values
    target_seq = args.seq
    target_ticks = None
    if args.ts:
        try:
            target_ticks = datetime_to_ticks(args.ts)
            print(f"Configured target sequence = {target_seq}, timestamp = {args.ts} (ticks: {target_ticks})")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    modified_schemas = 0
    modified_repl_statuses = 0
    modified_replications = 0

    # 1. Update DBMMSchemas name (e.g. SYNITI -> TBLIBTST)
    for schema in root.findall(".//DBMMSchemas"):
        name_elem = schema.find("Name")
        if name_elem is not None and name_elem.text == args.src_lib:
            name_elem.text = args.trg_lib
            modified_schemas += 1
            print(f"Updated schema Name from {args.src_lib} to {args.trg_lib}")

    # 2. Update DBMMReplStatuses properties and sequence/timestamps
    for status in root.findall(".//DBMMReplStatuses"):
        repl_id_elem = status.find("ReplicationID")
        repl_id = repl_id_elem.text if repl_id_elem is not None else "Unknown"

        props_elem = status.find("Properties")
        updated_props = False
        if props_elem is not None and props_elem.text:
            props = props_elem.text
            new_props = props
            # Map libraries, journals, receivers in property string
            new_props = new_props.replace(f"ReceiverLibrary={args.src_lib}", f"ReceiverLibrary={args.trg_lib}")
            new_props = new_props.replace(f"JournalLibrary={args.src_lib}", f"JournalLibrary={args.trg_lib}")
            new_props = new_props.replace(f"JournalName={args.src_jrn}", f"JournalName={args.trg_jrn}")
            new_props = new_props.replace(f"ReceiverName={args.src_rcv}", f"ReceiverName={args.trg_rcv}")

            if new_props != props:
                props_elem.text = new_props
                updated_props = True

        updated_seq_ts = False
        # Update Transaction ID
        if target_seq:
            tx_id_elem = status.find("TransactionID")
            if tx_id_elem is not None:
                tx_id_elem.text = target_seq
                updated_seq_ts = True

        # Update Transaction Timestamp
        if target_ticks:
            tx_ts_elem = status.find("TransactionTS")
            if tx_ts_elem is not None:
                tx_ts_elem.text = target_ticks
                updated_seq_ts = True

        if updated_props or updated_seq_ts:
            modified_repl_statuses += 1
            log_msg = f"Updated status entry for ReplicationID {repl_id}:"
            if updated_props:
                log_msg += " properties modified"
            if updated_seq_ts:
                log_msg += f" (Seq={target_seq}, TS_ticks={target_ticks})"
            print(log_msg)

    # 3. Update DBMMReplications properties
    for repl in root.findall(".//DBMMReplications"):
        repl_id_elem = repl.find("ReplicationID")
        repl_id = repl_id_elem.text if repl_id_elem is not None else "Unknown"
        name_elem = repl.find("Name")
        repl_name = name_elem.text if name_elem is not None else "Unknown"

        props_elem = repl.find("Properties")
        if props_elem is not None and props_elem.text:
            props = props_elem.text
            new_props = props
            new_props = new_props.replace(f"ReceiverLibrary={args.src_lib}", f"ReceiverLibrary={args.trg_lib}")
            new_props = new_props.replace(f"JournalLibrary={args.src_lib}", f"JournalLibrary={args.trg_lib}")
            new_props = new_props.replace(f"JournalName={args.src_jrn}", f"JournalName={args.trg_jrn}")

            if new_props != props:
                props_elem.text = new_props
                modified_replications += 1
                print(f"Updated replication properties for {repl_name} (ID {repl_id})")

    # Create backup and write file
    backup_path = args.xml + ".bak_script"
    if os.path.exists(args.xml):
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.rename(args.xml, backup_path)
        print(f"Created backup of original file at {backup_path}")

    tree.write(args.xml, encoding="utf-8", xml_declaration=True)
    print(f"Successfully wrote updated metadata XML back to {args.xml}")
    print(f"Summary: Modified {modified_schemas} schemas, {modified_repl_statuses} status entries, {modified_replications} replication configs.")

if __name__ == "__main__":
    main()
