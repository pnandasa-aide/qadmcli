"""Journal operations for AS400 tables."""

import logging
from typing import Any

from ..models.journal import JournalEntry, JournalInfo, JournalReceiverInfo
from .connection import AS400ConnectionManager

logger = logging.getLogger("qadmcli")


class JournalManager:
    """Manages journal operations for AS400 tables."""
    
    # Journal entry type mappings
    ENTRY_TYPES = {
        "PT": "INSERT",      # Put - Insert
        "UP": "UPDATE",      # Update
        "DL": "DELETE",      # Delete
        "BR": "BEFORE",      # Before image
        "UR": "AFTER",       # After image
        "DR": "DIRECT",      # Direct entry
    }
    
    def __init__(self, connection: AS400ConnectionManager):
        self.conn = connection
    
    def list_journals(self, library: str | None = None) -> list[dict[str, Any]]:
        """List all journals with their sizes.
        
        Args:
            library: Optional library filter
            
        Returns:
            List of journal information dictionaries
        """
        sql = """
            SELECT 
                JOURNAL_LIBRARY,
                JOURNAL_NAME,
                COUNT(*) as RECEIVER_COUNT,
                SUM(NUMBER_OF_JOURNAL_ENTRIES) as TOTAL_ENTRIES,
                MAX(CASE WHEN STATUS = 'ATTACHED' THEN JOURNAL_RECEIVER_NAME END) as ATTACHED_RECEIVER
            FROM QSYS2.JOURNAL_RECEIVER_INFO
            WHERE 1=1
        """
        params = []
        if library:
            sql += " AND JOURNAL_LIBRARY = ?"
            params.append(library.upper())
        
        sql += """
            GROUP BY JOURNAL_LIBRARY, JOURNAL_NAME
            ORDER BY TOTAL_ENTRIES DESC
        """
        
        cursor = self.conn.execute(sql, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        
        journals = []
        for row in rows:
            journals.append({
                'journal_library': str(row[0]) if row[0] else '',
                'journal_name': str(row[1]) if row[1] else '',
                'receiver_count': int(row[2]) if row[2] else 0,
                'total_entries': int(row[3]) if row[3] else 0,
                'attached_receiver': str(row[4]) if row[4] else None
            })
        
        return journals
    
    def is_journaled(self, table_name: str, library: str) -> bool:
        """Check if table is journaled using JOURNALED_OBJECTS view."""
        sql = """
            SELECT COUNT(*) 
            FROM QSYS2.JOURNALED_OBJECTS 
            WHERE OBJECT_NAME = ? 
            AND OBJECT_LIBRARY = ?
            AND OBJECT_TYPE = '*FILE'
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        
        return row[0] > 0 if row else False
    
    def get_receiver_chain(self, journal_name: str, library: str) -> list[dict[str, Any]]:
        """Get journal receiver chain with details.
        
        Args:
            journal_name: Name of the journal
            library: Library containing the journal
            
        Returns:
            List of receiver information dictionaries
        """
        sql = """
            SELECT 
                JOURNAL_RECEIVER_LIBRARY,
                JOURNAL_RECEIVER_NAME,
                NUMBER_OF_JOURNAL_ENTRIES,
                STATUS,
                SIZE
            FROM QSYS2.JOURNAL_RECEIVER_INFO
            WHERE JOURNAL_LIBRARY = ?
              AND JOURNAL_NAME = ?
            ORDER BY 
                CASE STATUS 
                    WHEN 'ATTACHED' THEN 1 
                    WHEN 'ONLINE' THEN 2 
                    ELSE 3 
                END,
                JOURNAL_RECEIVER_NAME
        """
        
        cursor = self.conn.execute(sql, (library.upper(), journal_name.upper()))
        rows = cursor.fetchall()
        cursor.close()
        
        receivers = []
        for row in rows:
            size_bytes = int(row[4]) if row[4] else 0
            size_mb = size_bytes / (1024 * 1024) if size_bytes else 0
            
            receivers.append({
                'receiver_library': str(row[0]) if row[0] else '',
                'receiver_name': str(row[1]) if row[1] else '',
                'entries': int(row[2]) if row[2] else 0,
                'status': str(row[3]) if row[3] else 'UNKNOWN',
                'size_bytes': size_bytes,
                'size_mb': size_mb
            })
        
        return receivers
    
    def get_cleanup_plan(self, journal_name: str, library: str, keep_recent: int = 2) -> dict[str, Any]:
        """Generate a cleanup plan for journal receivers.
        
        Args:
            journal_name: Name of the journal
            library: Library containing the journal
            keep_recent: Number of recent receivers to keep (excluding attached)
            
        Returns:
            Cleanup plan dictionary
        """
        receivers = self.get_receiver_chain(journal_name, library)
        
        # Separate receivers by status
        attached = [r for r in receivers if r['status'] == 'ATTACHED']
        online = [r for r in receivers if r['status'] == 'ONLINE']
        others = [r for r in receivers if r['status'] not in ('ATTACHED', 'ONLINE')]
        
        # Keep attached + N most recent online
        to_keep = attached.copy()
        if len(online) > keep_recent:
            # Keep the most recent N online receivers
            to_keep.extend(online[-keep_recent:])
            to_delete = online[:-keep_recent]
        else:
            to_delete = []
        
        # Add others to delete list
        to_delete.extend(others)
        
        total_space = sum(r['size_mb'] for r in to_delete)
        total_entries = sum(r['entries'] for r in to_delete)
        
        return {
            'journal_library': library.upper(),
            'journal_name': journal_name.upper(),
            'keeping': len(to_keep),
            'deleting': len(to_delete),
            'space_mb': total_space,
            'entries': total_entries,
            'to_keep': to_keep,
            'to_delete': to_delete
        }
    
    def execute_cleanup(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute cleanup plan by deleting old receivers.
        
        Args:
            plan: Cleanup plan from get_cleanup_plan()
            
        Returns:
            List of deletion results
        """
        results = []
        
        for receiver in plan['to_delete']:
            try:
                # Build delete command
                cmd = f"DLTJRNRCV JRNRCV({receiver['receiver_library']}/{receiver['receiver_name']})"
                sql = "CALL QSYS2.QCMDEXC(?, ?)"
                cmd_bytes = cmd.encode('utf-8')
                
                cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
                cursor.close()
                
                results.append({
                    'receiver_name': receiver['receiver_name'],
                    'success': True,
                    'error': None
                })
                logger.info(f"Deleted receiver: {receiver['receiver_name']}")
                
            except Exception as e:
                results.append({
                    'receiver_name': receiver['receiver_name'],
                    'success': False,
                    'error': str(e)
                })
                logger.error(f"Failed to delete receiver {receiver['receiver_name']}: {e}")
        
        return results
    
    def get_journal_info(self, table_name: str, library: str, skip_entry_range: bool = False) -> JournalInfo:
        """Get journal information for a table using JOURNALED_OBJECTS view.
        
        Args:
            table_name: Name of the table
            library: Library containing the table
            skip_entry_range: If True, skip the slow entry range query (for large journals)
        """
        import time
        start_time = time.time()
        
        # First check if table exists
        sql = """
            SELECT TABLE_NAME, TABLE_SCHEMA
            FROM QSYS2.SYSTABLES 
            WHERE SYSTEM_TABLE_NAME = ? 
            AND SYSTEM_TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            raise ValueError(f"Table {library}.{table_name} not found")
        
        # Get journal info from JOURNALED_OBJECTS
        sql = """
            SELECT 
                JOURNAL_LIBRARY,
                JOURNAL_NAME,
                JOURNAL_IMAGES
            FROM QSYS2.JOURNALED_OBJECTS 
            WHERE OBJECT_NAME = ? 
            AND OBJECT_LIBRARY = ?
            AND OBJECT_TYPE = '*FILE'
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        
        logger.debug(f"JOURNALED_OBJECTS query result: row={row}")
        
        # Handle various None/empty cases from database
        journal_lib = None
        journal_name = None
        journal_images = None
        if row:
            journal_lib = row[0] if row[0] else None
            journal_name = row[1] if row[1] else None
            journal_images = row[2] if row[2] else None
            # Convert to string if not None
            if journal_lib is not None:
                journal_lib = str(journal_lib).strip() or None
            if journal_name is not None:
                journal_name = str(journal_name).strip() or None
            if journal_images is not None:
                journal_images = str(journal_images).strip() or None
        
        is_journaled = journal_lib is not None and journal_name is not None
        
        logger.debug(f"Parsed journal info: lib={journal_lib}, name={journal_name}, is_journaled={is_journaled}")
        
        info = JournalInfo(
            table_name=table_name.upper(),
            table_library=library.upper(),
            is_journaled=is_journaled,
            journal_library=journal_lib,
            journal_name=journal_name,
            journal_images=journal_images,
        )
        
        # If journaled, get receiver info and entry range
        if info.is_journaled and info.journal_library and info.journal_name:
            self._populate_receiver_info(info)
            if not skip_entry_range:
                range_start = time.time()
                self._populate_entry_range(info)
                range_time = time.time() - range_start
                logger.info(f"Entry range query took {range_time:.2f} seconds")
            else:
                logger.info("Skipping entry range query (fast mode)")
        
        total_time = time.time() - start_time
        logger.info(f"Total journal info query took {total_time:.2f} seconds")
        
        return info
    
    def _populate_receiver_info(self, info: JournalInfo) -> None:
        """Populate journal receiver information."""
        sql = """
            SELECT 
                JOURNAL_LIBRARY,
                JOURNAL_NAME,
                ATTACHED_JOURNAL_RECEIVER_LIBRARY,
                ATTACHED_JOURNAL_RECEIVER_NAME
            FROM QSYS2.JOURNAL_INFO
            WHERE JOURNAL_LIBRARY = ?
            AND JOURNAL_NAME = ?
        """
        try:
            cursor = self.conn.execute(sql, (info.journal_library, info.journal_name))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                info.journal_receiver_library = str(row[2]) if row[2] else None
                info.journal_receiver_name = str(row[3]) if row[3] else None
        except Exception as e:
            logger.warning(f"Could not get receiver info: {e}")
    
    def _populate_entry_range(self, info: JournalInfo) -> None:
        """Populate entry sequence range from journal receiver info."""
        # Get receiver info (attach/detach times)
        sql = """
            SELECT 
                FIRST_SEQUENCE_NUMBER,
                LAST_SEQUENCE_NUMBER,
                NUMBER_OF_JOURNAL_ENTRIES,
                ATTACH_TIMESTAMP,
                DETACH_TIMESTAMP,
                JOURNAL_RECEIVER_NAME,
                JOURNAL_RECEIVER_LIBRARY,
                STATUS
            FROM QSYS2.JOURNAL_RECEIVER_INFO
            WHERE JOURNAL_LIBRARY = ?
              AND JOURNAL_NAME = ?
              AND STATUS = 'ATTACHED'
            FETCH FIRST 1 ROW ONLY
        """
        try:
            cursor = self.conn.execute(sql, (info.journal_library, info.journal_name))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                # Receiver info
                info.journal_receiver_name = str(row[5]) if row[5] else None
                info.journal_receiver_library = str(row[6]) if row[6] else None
                info.receiver_attach_timestamp = str(row[3]) if row[3] else None
                info.receiver_detach_timestamp = str(row[4]) if row[4] else None
                
                # Now get table-specific entry range from DISPLAY_JOURNAL
                self._populate_table_entry_range(info)
        except Exception as e:
            logger.debug(f"Entry range query failed: {e}")
            logger.warning(f"Could not get entry range: {e}")
    
    def _populate_table_entry_range(self, info: JournalInfo) -> None:
        """Get entry range specific to the table."""
        # Try both system name and SQL name for OBJECT
        # First, get the system name from SYSTABLES
        system_name = info.table_name
        try:
            cursor = self.conn.execute(
                "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
                (info.table_name, info.table_library)
            )
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                system_name = str(row[0]).strip()  # Strip trailing spaces
                logger.debug(f"Using system table name: '{system_name}'")
        except Exception:
            pass
        
        # Try with system name first
        # OBJECT column format: "TABLE_NAME     LIBRARY_NAME    TABLE_NAME     "
        # It's 30 chars with the table name appearing twice and lots of padding
        sql = """
            SELECT 
                MIN(SEQUENCE_NUMBER),
                MAX(SEQUENCE_NUMBER),
                COUNT(*),
                MIN(ENTRY_TIMESTAMP),
                MAX(ENTRY_TIMESTAMP)
            FROM TABLE (
                QSYS2.DISPLAY_JOURNAL(
                    JOURNAL_LIBRARY => ?,
                    JOURNAL_NAME => ?
                )
            )
            WHERE OBJECT LIKE ?
        """
        try:
            # Use LIKE pattern to match the table name anywhere in the OBJECT column
            # The OBJECT format is: "TABLE_NAME<spaces>LIBRARY_NAME<spaces>TABLE_NAME<spaces>"
            object_pattern = f"%{system_name}%"
            logger.debug(f"Querying table entry range for OBJECT LIKE '{object_pattern}'")
            cursor = self.conn.execute(sql, (
                info.journal_library, 
                info.journal_name, 
                object_pattern
            ))
            row = cursor.fetchone()
            cursor.close()
            
            if row and row[0] is not None:
                info.oldest_entry_sequence = row[0]
                info.newest_entry_sequence = row[1]
                info.total_entries = row[2]
                info.oldest_entry_timestamp = str(row[3]) if row[3] else None
                info.newest_entry_timestamp = str(row[4]) if row[4] else None
                logger.debug(f"Found {row[2]} entries for table")
            else:
                logger.debug("No entries found with system name, trying SQL name")
                # Try with SQL name
                sql_object_pattern = f"%{info.table_name}%"
                cursor = self.conn.execute(sql, (
                    info.journal_library, 
                    info.journal_name, 
                    sql_object_pattern
                ))
                row = cursor.fetchone()
                cursor.close()
                if row and row[0] is not None:
                    info.oldest_entry_sequence = row[0]
                    info.newest_entry_sequence = row[1]
                    info.total_entries = row[2]
                    info.oldest_entry_timestamp = str(row[3]) if row[3] else None
                    info.newest_entry_timestamp = str(row[4]) if row[4] else None
                    logger.debug(f"Found {row[2]} entries with SQL name")
        except Exception as e:
            logger.debug(f"Table entry range query failed: {e}")
    
    def _check_journal_permission(self, journal_library: str, user: str) -> dict[str, Any]:
        """Check if user has permission to use journal in the specified library."""
        sql = """
            SELECT 
                OBJECT_AUTHORITY,
                DATA_READ,
                DATA_ADD
            FROM QSYS2.OBJECT_PRIVILEGES
            WHERE OBJECT_SCHEMA = ?
            AND OBJECT_NAME = ?
            AND AUTHORIZATION_NAME = ?
        """
        try:
            cursor = self.conn.execute(sql, (journal_library, journal_library, user))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                return {
                    "has_access": True,
                    "object_authority": row[0],
                    "can_read": row[1] == "YES",
                    "can_add": row[2] == "YES",
                    "can_manage_journal": row[0] in ("*ALL", "*CHANGE"),
                }
            else:
                return {"has_access": False}
        except Exception as e:
            logger.warning(f"Could not check journal permissions: {e}")
            return {"has_access": False, "error": str(e)}
    
    def enable_journaling(
        self,
        table_name: str,
        library: str,
        journal_library: str | None = None,
        journal_name: str | None = None
    ) -> dict[str, Any]:
        """Enable journaling for a table."""
        # Use defaults if not specified
        if not journal_library:
            journal_library = self.conn.config.defaults.journal_library
        if not journal_name:
            journal_name = "QSQJRN"  # Common default
        
        # Check user permissions on journal library
        user = self.conn.config.as400.user
        perm = self._check_journal_permission(journal_library, user)
        
        if not perm.get("has_access"):
            raise PermissionError(
                f"User {user} does not have access to journal library {journal_library}. "
                "Contact your AS400 administrator to grant *USE or higher authority."
            )
        
        # Check if journal exists
        if not self._journal_exists(journal_library, journal_name):
            raise ValueError(
                f"Journal {journal_library}.{journal_name} does not exist. "
                "Please create it first or specify a different journal."
            )
        
        # Build STRJRNPF command
        cmd = (
            f"STRJRNPF FILE({library}/{table_name}) "
            f"JRN({journal_library}/{journal_name}) "
            f"IMAGES(*BOTH) OMTJRNE(*OPNCLO)"
        )
        
        # Execute via QCMDEXC
        result = self._execute_command(cmd)
        
        if result["success"]:
            logger.info(
                f"Enabled journaling for {library}.{table_name} "
                f"using {journal_library}.{journal_name}"
            )
            return {
                "success": True,
                "table": f"{library}.{table_name}",
                "journal": f"{journal_library}.{journal_name}",
            }
        else:
            raise RuntimeError(f"Failed to enable journaling: {result['message']}")
    
    def disable_journaling(self, table_name: str, library: str) -> dict[str, Any]:
        """Disable journaling for a table."""
        cmd = f"ENDJRNPF FILE({library}/{table_name}) JRN(*FILE)"
        
        result = self._execute_command(cmd)
        
        if result["success"]:
            logger.info(f"Disabled journaling for {library}.{table_name}")
            return {
                "success": True,
                "table": f"{library}.{table_name}",
            }
        else:
            raise RuntimeError(f"Failed to disable journaling: {result['message']}")
    
    def create_journal_receiver(
        self,
        receiver_name: str,
        library: str,
        threshold: str = "*NONE"
    ) -> dict[str, Any]:
        """Create a journal receiver."""
        cmd = f"CRTJRNRCV JRNRCV({library}/{receiver_name})"
        
        if threshold != "*NONE":
            cmd += f" THRESHOLD({threshold})"
        
        result = self._execute_command(cmd)
        
        if result["success"]:
            logger.info(f"Created journal receiver {library}.{receiver_name}")
            return {
                "success": True,
                "receiver": f"{library}.{receiver_name}",
                "threshold": threshold,
            }
        else:
            raise RuntimeError(f"Failed to create journal receiver: {result['message']}")
    
    def create_journal(
        self,
        journal_name: str,
        library: str,
        receiver_name: str,
        receiver_library: str | None = None,
        msg_queue: str = "*NONE"
    ) -> dict[str, Any]:
        """Create a journal attached to a receiver."""
        recv_lib = receiver_library or library
        
        cmd = f"CRTJRN JRN({library}/{journal_name}) JRNRCV({recv_lib}/{receiver_name})"
        
        if msg_queue != "*NONE":
            cmd += f" MSGQ({msg_queue})"
        
        result = self._execute_command(cmd)
        
        if result["success"]:
            logger.info(f"Created journal {library}.{journal_name}")
            return {
                "success": True,
                "journal": f"{library}.{journal_name}",
                "receiver": f"{recv_lib}.{receiver_name}",
            }
        else:
            raise RuntimeError(f"Failed to create journal: {result['message']}")
    
    def rollover_journal(
        self,
        journal_name: str,
        library: str,
        new_receiver_name: str | None = None,
        receiver_library: str | None = None
    ) -> dict[str, Any]:
        """Rollover journal to a new receiver.
        
        This uses CHGJRN with JRNRCV(*GEN) to create a new receiver and attach it,
        automatically detaching the current receiver.
        
        Args:
            journal_name: Name of the journal
            library: Library containing the journal
            new_receiver_name: Optional name for new receiver (auto-generated if None)
            receiver_library: Optional library for new receiver (defaults to journal library)
            
        Returns:
            Dictionary with rollover results
        """
        recv_lib = receiver_library or library
        
        # Build CHGJRN command
        if new_receiver_name:
            # Use specified receiver name
            cmd = f"CHGJRN JRN({library}/{journal_name}) JRNRCV({recv_lib}/{new_receiver_name})"
        else:
            # Auto-generate receiver name
            cmd = f"CHGJRN JRN({library}/{journal_name}) JRNRCV(*GEN)"
        
        result = self._execute_command(cmd)
        
        if result["success"]:
            logger.info(f"Rollover complete for journal {library}.{journal_name}")
            
            # Get the new attached receiver
            receivers = self.get_receiver_chain(journal_name, library)
            attached = [r for r in receivers if r['status'] == 'ATTACHED']
            new_receiver = attached[0]['receiver_name'] if attached else 'Unknown'
            
            return {
                "success": True,
                "journal": f"{library}.{journal_name}",
                "new_receiver": new_receiver,
                "receiver_library": recv_lib,
            }
        else:
            raise RuntimeError(f"Failed to rollover journal: {result['message']}")
    
    def get_journal_entries(
        self,
        table_name: str,
        library: str,
        limit: int = 100,
        entry_type: str | None = None,
        starting_sequence: int | None = None,
    ) -> list[JournalEntry]:
        """Get journal entries for a table."""
        # First get journal info
        info = self.get_journal_info(table_name, library)
        
        if not info.is_journaled:
            raise ValueError(f"Table {library}.{table_name} is not journaled")
        
        # Get system name for the table (DISPLAY_JOURNAL uses system names)
        system_name = table_name.upper()
        try:
            cursor = self.conn.execute(
                "SELECT SYSTEM_TABLE_NAME FROM QSYS2.SYSTABLES WHERE TABLE_NAME = ? AND TABLE_SCHEMA = ?",
                (table_name.upper(), library.upper())
            )
            row = cursor.fetchone()
            cursor.close()
            if row and row[0]:
                system_name = str(row[0]).strip().upper()  # Strip trailing spaces
                logger.debug(f"Using system table name for entries: '{system_name}'")
        except Exception as e:
            logger.debug(f"Could not get system name: {e}")
        
        # Build entry types filter - default to all types if not specified
        entry_types = entry_type.upper() if entry_type else "*ALL"
        
        # Build SQL - filter by OBJECT (table name) only
        # Note: DISPLAY_JOURNAL doesn't have OBJECT_LIBRARY column
        sql = """
            SELECT 
                SEQUENCE_NUMBER,
                ENTRY_TIMESTAMP,
                JOB_NAME,
                JOB_USER,
                JOB_NUMBER,
                PROGRAM_NAME,
                JOURNAL_CODE,
                JOURNAL_ENTRY_TYPE,
                OBJECT,
                OBJECT_TYPE,
                ENTRY_DATA
            FROM TABLE (
                QSYS2.DISPLAY_JOURNAL(
                    JOURNAL_LIBRARY => ?,
                    JOURNAL_NAME => ?,
                    JOURNAL_ENTRY_TYPES => ?
                )
            )
            WHERE OBJECT = ?
        """
        
        # OBJECT column contains "TABLE_NAME LIBRARY_NAME" format
        object_value = f"{system_name} {library.upper()}"
        logger.debug(f"Using OBJECT value: '{object_value}'")
        
        params = [
            info.journal_library,
            info.journal_name,
            entry_types,
            object_value,
        ]
        
        if starting_sequence:
            sql += " AND SEQUENCE_NUMBER >= ?"
            params.append(starting_sequence)
        
        sql += " ORDER BY SEQUENCE_NUMBER DESC FETCH FIRST ? ROWS ONLY"
        params.append(limit)
        
        logger.debug(f"Querying journal entries with params: {params}")
        cursor = self.conn.execute(sql, tuple(params))
        
        entries = []
        for row in cursor.fetchall():
            # Read BLOB data if present
            raw_data = None
            if row[10]:
                try:
                    # Handle AS400JDBCBlobLocator - need to get bytes
                    blob = row[10]
                    if hasattr(blob, 'getBytes'):
                        # Use getBytes method for AS400JDBCBlobLocator
                        length = blob.length()
                        if length > 0:
                            bytes_data = blob.getBytes(1, int(length))
                            # Convert Java byte[] to Python bytes
                            if bytes_data:
                                try:
                                    # Try direct bytes conversion
                                    raw_data = bytes(bytes_data).decode('utf-8', errors='ignore')
                                except:
                                    # Fallback: convert to string representation
                                    raw_data = str(bytes_data)
                    elif hasattr(blob, 'read'):
                        # It's a stream, read it
                        raw_data = blob.read()
                        if isinstance(raw_data, bytes):
                            raw_data = raw_data.decode('utf-8', errors='ignore')
                    else:
                        # It's already a string or other type
                        raw_data = str(blob)
                except Exception as e:
                    logger.debug(f"Could not read blob data: {e}")
                    raw_data = str(row[10])
            
            entry = JournalEntry(
                entry_number=row[0],
                entry_timestamp=str(row[1]) if row[1] else None,
                job_name=str(row[2]) if row[2] else None,
                job_user=str(row[3]) if row[3] else None,
                job_number=str(row[4]) if row[4] else None,
                program_name=str(row[5]) if row[5] else None,
                code=str(row[6]) if row[6] else None,
                entry_type=str(row[7]) if row[7] else None,
                object_name=str(row[8]).strip() if row[8] else None,
                object_library=library.upper(),  # Use the provided library
                object_type=str(row[9]) if row[9] else None,
                raw_entry_data=raw_data,
            )
            
            # Try to parse entry data for record-level entries
            if entry.code == "R" and entry.raw_entry_data:
                self._parse_entry_data(entry)
            
            entries.append(entry)
        
        cursor.close()
        logger.debug(f"Found {len(entries)} journal entries")
        return entries
    
    def _parse_entry_data(self, entry: JournalEntry) -> None:
        """Parse journal entry data into before/after images."""
        # This is a simplified parser - real implementation would need
        # to understand the specific table structure
        # For now, we store raw data
        try:
            if entry.raw_entry_data:
                # Attempt basic parsing - this would need enhancement
                # based on actual entry data format
                entry.after_image = {"raw_data": entry.raw_entry_data[:200]}
        except Exception as e:
            logger.debug(f"Could not parse entry data: {e}")
    
    def _journal_exists(self, library: str, name: str) -> bool:
        """Check if journal exists."""
        sql = """
            SELECT COUNT(*) 
            FROM QSYS2.JOURNAL_INFO 
            WHERE JOURNAL_LIBRARY = ? AND JOURNAL_NAME = ?
        """
        try:
            cursor = self.conn.execute(sql, (library.upper(), name.upper()))
            row = cursor.fetchone()
            cursor.close()
            return row[0] > 0
        except Exception:
            return False
    
    def _execute_command(self, cmd: str) -> dict[str, Any]:
        """Execute CL command via QCMDEXC."""
        # Escape single quotes
        escaped_cmd = cmd.replace("'", "''")
        
        sql = f"CALL QSYS2.QCMDEXC('{escaped_cmd}')"
        
        try:
            cursor = self.conn.execute(sql)
            cursor.close()
            return {"success": True, "message": "Command executed successfully"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def get_receivers(
        self,
        journal_library: str,
        journal_name: str
    ) -> list[JournalReceiverInfo]:
        """Get journal receiver chain."""
        sql = """
            SELECT 
                RECEIVER_LIBRARY,
                RECEIVER_NAME,
                ATTACHED,
                CREATED_TIMESTAMP,
                NUMBER_OF_ENTRIES,
                SIZE
            FROM TABLE (
                QSYS2.JOURNAL_RECEIVER_INFO(
                    JOURNAL_LIBRARY => ?,
                    JOURNAL_NAME => ?
                )
            )
            ORDER BY CREATED_TIMESTAMP
        """
        
        cursor = self.conn.execute(sql, (journal_library.upper(), journal_name.upper()))
        receivers = []
        
        for row in cursor.fetchall():
            receivers.append(JournalReceiverInfo(
                receiver_library=row[0],
                receiver_name=row[1],
                attached=row[2] == "YES" if row[2] else False,
                created=str(row[3]) if row[3] else None,
                entries=row[4],
                size=row[5],
            ))
        
        cursor.close()
        return receivers
