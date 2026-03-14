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
    
    def is_journaled(self, table_name: str, library: str) -> bool:
        """Check if table is journaled."""
        sql = """
            SELECT JOURNALED 
            FROM QSYS2.SYSTABLES 
            WHERE SYSTEM_TABLE_NAME = ? 
            AND SYSTEM_TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            return row[0] == "YES"
        return False
    
    def get_journal_info(self, table_name: str, library: str) -> JournalInfo:
        """Get journal information for a table."""
        sql = """
            SELECT 
                SYSTEM_TABLE_NAME,
                SYSTEM_TABLE_SCHEMA,
                JOURNALED,
                JOURNAL_LIBRARY,
                JOURNAL_NAME
            FROM QSYS2.SYSTABLES 
            WHERE SYSTEM_TABLE_NAME = ? 
            AND SYSTEM_TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            raise ValueError(f"Table {library}.{table_name} not found")
        
        info = JournalInfo(
            table_name=row[0],
            table_library=row[1],
            is_journaled=row[2] == "YES" if row[2] else False,
            journal_library=row[3],
            journal_name=row[4],
        )
        
        # If journaled, get receiver info and entry range
        if info.is_journaled and info.journal_library and info.journal_name:
            self._populate_receiver_info(info)
            self._populate_entry_range(info)
        
        return info
    
    def _populate_receiver_info(self, info: JournalInfo) -> None:
        """Populate journal receiver information."""
        sql = """
            SELECT 
                JOURNAL_LIBRARY,
                JOURNAL_NAME,
                CURRENT_RECEIVER_LIBRARY,
                CURRENT_RECEIVER
            FROM QSYS2.JOURNAL_INFO
            WHERE JOURNAL_LIBRARY = ?
            AND JOURNAL_NAME = ?
        """
        try:
            cursor = self.conn.execute(sql, (info.journal_library, info.journal_name))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                info.journal_receiver_library = row[2]
                info.journal_receiver_name = row[3]
        except Exception as e:
            logger.warning(f"Could not get receiver info: {e}")
    
    def _populate_entry_range(self, info: JournalInfo) -> None:
        """Populate entry sequence range."""
        # Get oldest and newest entries
        sql = """
            SELECT 
                MIN(SEQUENCE_NUMBER),
                MAX(SEQUENCE_NUMBER),
                MIN(TIMESTAMP),
                MAX(TIMESTAMP),
                COUNT(*)
            FROM TABLE (
                QSYS2.DISPLAY_JOURNAL(
                    JOURNAL_LIBRARY => ?,
                    JOURNAL_NAME => ?,
                    JOURNAL_ENTRY_TYPES => 'R',
                    OBJECT_LIBRARY => ?,
                    OBJECT_NAME => ?
                )
            )
        """
        try:
            cursor = self.conn.execute(sql, (
                info.journal_library,
                info.journal_name,
                info.table_library,
                info.table_name
            ))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                info.oldest_entry_sequence = row[0]
                info.newest_entry_sequence = row[1]
                info.oldest_entry_timestamp = str(row[2]) if row[2] else None
                info.newest_entry_timestamp = str(row[3]) if row[3] else None
                info.total_entries = row[4]
        except Exception as e:
            logger.warning(f"Could not get entry range: {e}")
    
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
        
        # Build entry types filter
        entry_types = entry_type.upper() if entry_type else "R"
        
        sql = """
            SELECT 
                SEQUENCE_NUMBER,
                TIMESTAMP,
                JOB_NAME,
                JOB_USER,
                JOB_NUMBER,
                PROGRAM_NAME,
                JOURNAL_CODE,
                JOURNAL_ENTRY_TYPE,
                OBJECT_LIBRARY,
                OBJECT_NAME,
                OBJECT_TYPE,
                ENTRY_DATA
            FROM TABLE (
                QSYS2.DISPLAY_JOURNAL(
                    JOURNAL_LIBRARY => ?,
                    JOURNAL_NAME => ?,
                    JOURNAL_ENTRY_TYPES => ?,
                    OBJECT_LIBRARY => ?,
                    OBJECT_NAME => ?,
                    STARTING_SEQUENCE_NUMBER => ?
                )
            )
            ORDER BY SEQUENCE_NUMBER DESC
            FETCH FIRST ? ROWS ONLY
        """
        
        cursor = self.conn.execute(sql, (
            info.journal_library,
            info.journal_name,
            entry_types,
            library.upper(),
            table_name.upper(),
            starting_sequence,
            limit
        ))
        
        entries = []
        for row in cursor.fetchall():
            entry = JournalEntry(
                entry_number=row[0],
                entry_timestamp=str(row[1]) if row[1] else None,
                job_name=row[2],
                job_user=row[3],
                job_number=row[4],
                program_name=row[5],
                code=row[6],
                entry_type=row[7],
                object_library=row[8],
                object_name=row[9],
                object_type=row[10],
                raw_entry_data=row[11] if row[11] else None,
            )
            
            # Try to parse entry data for record-level entries
            if entry.code == "R" and entry.raw_entry_data:
                self._parse_entry_data(entry)
            
            entries.append(entry)
        
        cursor.close()
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
