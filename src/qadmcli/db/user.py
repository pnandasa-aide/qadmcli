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
            "permissions": []
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
        
        return result
    
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
