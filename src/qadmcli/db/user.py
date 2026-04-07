"""User management operations."""

import logging
from typing import Any

from .connection import AS400ConnectionManager

logger = logging.getLogger("qadmcli")


class UserManager:
    """Manages AS400 user operations."""
    
    def __init__(self, connection: AS400ConnectionManager):
        self.conn = connection
    
    def check_user(self, username: str, library: str | None = None, object_name: str | None = None) -> dict[str, Any]:
        """Check if user exists and get permissions."""
        result = {
            "exists": False,
            "user": username.upper(),
            "permissions": [],
            "journal_permissions": []
        }
        
        # Check user existence
        sql = """
            SELECT 
                AUTHORIZATION_NAME,
                USER_CLASS_NAME,
                STATUS,
                GROUP_PROFILE_NAME,
                SPECIAL_AUTHORITIES
            FROM QSYS2.USER_INFO
            WHERE AUTHORIZATION_NAME = ?
        """
        cursor = self.conn.execute(sql, (username.upper(),))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            result["exists"] = True
            result["user_class"] = row[1]
            result["status"] = row[2]
            result["group_profile"] = row[3]
            result["special_authorities"] = row[4]
        
        # Get permissions if library specified
        if library and result["exists"]:
            obj_filter = object_name.upper() if object_name else "*ALL"
            
            # Query object privileges using OBJECT_STATISTICS
            perm_sql = """
                SELECT *
                FROM TABLE(QSYS2.OBJECT_STATISTICS(?, 'FILE', ?))
            """
            cursor = self.conn.execute(perm_sql, (library.upper(), obj_filter))
            
            for row in cursor.fetchall():
                result["permissions"].append({
                    "object": str(row[0]) if row[0] else "",  # OBJNAME
                    "object_type": str(row[1]) if row[1] else "*FILE",  # OBJTYPE
                    "authority": "*CHANGE"  # Default assumption for accessible objects
                })
            cursor.close()
            
            # Query journal and journal receiver permissions
            journal_sql = """
                SELECT 
                    OBJECT_NAME,
                    OBJECT_TYPE,
                    OBJECT_AUTHORITY
                FROM QSYS2.OBJECT_PRIVILEGES
                WHERE AUTHORIZATION_NAME = ?
                  AND OBJECT_SCHEMA = ?
                  AND OBJECT_TYPE IN ('*JRN', '*JRNRCV')
                ORDER BY OBJECT_TYPE, OBJECT_NAME
            """
            cursor = self.conn.execute(journal_sql, (username.upper(), library.upper()))
            
            for row in cursor.fetchall():
                result["journal_permissions"].append({
                    "object": str(row[0]) if row[0] else "",
                    "object_type": str(row[1]) if row[1] else "",
                    "authority": str(row[2]) if row[2] else "*NONE"
                })
            cursor.close()
        
        return result
    
    def check_table_permissions_with_journal(
        self, 
        username: str, 
        table_name: str, 
        table_library: str
    ) -> dict[str, Any]:
        """Check user permissions for a specific table and its related journal objects.
        
        Returns a consolidated view showing:
        - Table permissions
        - Journal permissions (even if journal is in different library)
        - Journal receiver permissions
        """
        result = {
            "user": username.upper(),
            "table": {
                "name": table_name.upper(),
                "library": table_library.upper(),
                "authority": None
            },
            "journal": {
                "name": None,
                "library": None,
                "authority": None
            },
            "journal_receiver": {
                "name": None,
                "library": None,
                "authority": None
            }
        }
        
        # 1. Check table permission
        table_sql = """
            SELECT OBJECT_AUTHORITY
            FROM QSYS2.OBJECT_PRIVILEGES
            WHERE AUTHORIZATION_NAME = ?
              AND OBJECT_SCHEMA = ?
              AND OBJECT_NAME = ?
              AND OBJECT_TYPE = '*FILE'
        """
        try:
            cursor = self.conn.execute(table_sql, (
                username.upper(), 
                table_library.upper(), 
                table_name.upper()
            ))
            row = cursor.fetchone()
            cursor.close()
            if row:
                result["table"]["authority"] = str(row[0]) if row[0] else "*NONE"
        except Exception as e:
            logger.debug(f"Could not get table permission: {e}")
        
        # 2. Get journal info for this table
        journal_sql = """
            SELECT 
                j.JOURNAL_NAME,
                j.JOURNAL_LIBRARY,
                r.ATTACHED_JOURNAL_RECEIVER_NAME,
                r.ATTACHED_JOURNAL_RECEIVER_LIBRARY
            FROM QSYS2.SYSTABLES t
            LEFT JOIN QSYS2.JOURNALED_OBJECTS j ON (
                t.TABLE_SCHEMA = j.OBJECT_LIBRARY 
                AND t.SYSTEM_TABLE_NAME = j.OBJECT_NAME
            )
            LEFT JOIN QSYS2.JOURNAL_INFO r ON (
                j.JOURNAL_LIBRARY = r.JOURNAL_LIBRARY
                AND j.JOURNAL_NAME = r.JOURNAL_NAME
            )
            WHERE t.TABLE_SCHEMA = ?
              AND t.TABLE_NAME = ?
            FETCH FIRST 1 ROW ONLY
        """
        try:
            cursor = self.conn.execute(journal_sql, (
                table_library.upper(),
                table_name.upper()
            ))
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                journal_name = str(row[0]) if row[0] else None
                journal_library = str(row[1]) if row[1] else None
                receiver_name = str(row[2]) if row[2] else None
                receiver_library = str(row[3]) if row[3] else None
                
                result["journal"]["name"] = journal_name
                result["journal"]["library"] = journal_library
                result["journal_receiver"]["name"] = receiver_name
                result["journal_receiver"]["library"] = receiver_library
                
                # 3. Check journal permission
                if journal_name and journal_library:
                    jrn_sql = """
                        SELECT OBJECT_AUTHORITY
                        FROM QSYS2.OBJECT_PRIVILEGES
                        WHERE AUTHORIZATION_NAME = ?
                          AND OBJECT_SCHEMA = ?
                          AND OBJECT_NAME = ?
                          AND OBJECT_TYPE = '*JRN'
                    """
                    cursor = self.conn.execute(jrn_sql, (
                        username.upper(),
                        journal_library.upper(),
                        journal_name.upper()
                    ))
                    row = cursor.fetchone()
                    cursor.close()
                    if row:
                        result["journal"]["authority"] = str(row[0]) if row[0] else "*NONE"
                
                # 4. Check journal receiver permission
                if receiver_name and receiver_library:
                    rcv_sql = """
                        SELECT OBJECT_AUTHORITY
                        FROM QSYS2.OBJECT_PRIVILEGES
                        WHERE AUTHORIZATION_NAME = ?
                          AND OBJECT_SCHEMA = ?
                          AND OBJECT_NAME = ?
                          AND OBJECT_TYPE = '*JRNRCV'
                    """
                    cursor = self.conn.execute(rcv_sql, (
                        username.upper(),
                        receiver_library.upper(),
                        receiver_name.upper()
                    ))
                    row = cursor.fetchone()
                    cursor.close()
                    if row:
                        result["journal_receiver"]["authority"] = str(row[0]) if row[0] else "*NONE"
                        
        except Exception as e:
            logger.debug(f"Could not get journal info: {e}")
        
        return result
    
    def create_library(self, library_name: str) -> dict[str, Any]:
        """Create a new library.
        
        Args:
            library_name: Name of the library to create
            
        Returns:
            Dictionary with creation results
        """
        cmd = f"CRTLIB LIB({library_name.upper()})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Created library {library_name.upper()}")
        return {
            "library": library_name.upper(),
            "created": True
        }
    
    def create_user(self, username: str, password: str | None = None) -> dict[str, Any]:
        """Create a new user profile."""
        # Use CRTUSRPRF command via QCMDEXC
        password_param = f"PASSWORD {password}" if password else ""
        
        cmd = f"CRTUSRPRF USRPRF({username.upper()}) {password_param} STATUS(*ENABLED)"
        
        # Execute via QCMDEXC
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Created user {username}")
        return {"user": username.upper(), "created": True}
    
    def delete_user(self, username: str) -> dict[str, Any]:
        """Delete a user profile."""
        cmd = f"DLTUSRPRF USRPRF({username.upper()})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Deleted user {username}")
        return {"user": username.upper(), "deleted": True}
    
    def change_password(self, username: str, password: str) -> dict[str, Any]:
        """Change user password."""
        cmd = f"CHGUSRPRF USRPRF({username.upper()}) PASSWORD({password})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Changed password for user {username}")
        return {"user": username.upper(), "password_changed": True}
    
    def grant_object_authority(self, username: str, library: str, object_name: str, authority: str, object_type: str = "*FILE") -> dict[str, Any]:
        """Grant object authority to user.
        
        Args:
            username: User to grant authority to
            library: Library containing the object
            object_name: Object name or *ALL
            authority: Authority level (*USE, *CHANGE, *ALL, etc.)
            object_type: Object type (*FILE, *JRN, *JRNRCV, *LIB, *ALL)
        """
        # For libraries, the object name is the library name itself
        # and the format is just LIBNAME not LIBNAME/LIBNAME
        if object_type == "*LIB":
            cmd = f"GRTOBJAUT OBJ({library.upper()}) OBJTYPE({object_type}) USER({username.upper()}) AUT({authority})"
        else:
            cmd = f"GRTOBJAUT OBJ({library.upper()}/{object_name}) OBJTYPE({object_type}) USER({username.upper()}) AUT({authority})"
        
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Granted {authority} authority to {username} on {library}/{object_name} ({object_type})")
        return {
            "user": username.upper(),
            "library": library.upper(),
            "object": object_name,
            "object_type": object_type,
            "authority": authority
        }
    
    def grant_library_permissions(self, username: str, library: str, object_name: str | None = None) -> dict[str, Any]:
        """Grant permissions on library objects."""
        obj_filter = object_name.upper() if object_name else "*ALL"
        
        # Grant on library
        cmd = f"GRTOBJAUT OBJ({library.upper()}) OBJTYPE(*LIB) USER({username.upper()}) AUT(*USE)"
        sql = "CALL QSYS2.QCMDEXC(?, ?)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        # Grant on objects
        cmd = f"GRTOBJAUT OBJ({library.upper()}/{obj_filter}) OBJTYPE(*ALL) USER({username.upper()}) AUT(*CHANGE)"
        cmd_bytes = cmd.encode('utf-8')
        cursor = self.conn.execute(sql, (cmd, len(cmd_bytes)))
        cursor.close()
        
        logger.info(f"Granted permissions to {username} on {library}/{obj_filter}")
        return {
            "user": username.upper(),
            "library": library.upper(),
            "objects": obj_filter
        }
    
    def list_permissions(self, username: str, library: str | None = None) -> dict[str, Any]:
        """List user permissions and authorities."""
        result = {
            "user": username.upper(),
            "object_authorities": []
        }
        
        # Get user info
        sql = """
            SELECT 
                USER_CLASS_NAME,
                GROUP_PROFILE_NAME,
                SPECIAL_AUTHORITIES
            FROM QSYS2.USER_INFO
            WHERE AUTHORIZATION_NAME = ?
        """
        cursor = self.conn.execute(sql, (username.upper(),))
        row = cursor.fetchone()
        cursor.close()
        
        if row:
            result["user_class"] = row[0]
            result["group_profile"] = row[1]
            # Parse special authorities
            spec_auths = row[2] if row[2] else ""
            result["special_authorities"] = [a.strip() for a in spec_auths.split() if a.strip()]
        
        # Get object authorities using OBJECT_STATISTICS
        lib_filter = library.upper() if library else "*ALL"
        
        perm_sql = """
            SELECT *
            FROM TABLE(QSYS2.OBJECT_STATISTICS(?, 'FILE', '*ALL'))
        """
        cursor = self.conn.execute(perm_sql, (lib_filter,))
        for row in cursor.fetchall():
            result["object_authorities"].append({
                "library": library.upper() if library else "*ALL",
                "object": str(row[0]) if row[0] else "",  # OBJNAME
                "object_type": str(row[1]) if row[1] else "*FILE",  # OBJTYPE
                "authority": "*CHANGE"  # Default for accessible objects
            })
        cursor.close()
        
        return result
