"""Table schema operations."""

import logging
import re
from typing import Any

from ..models.table import TableConfig, TableInfo
from .connection import AS400ConnectionManager

logger = logging.getLogger("qadmcli")


class SchemaManager:
    """Manages database schema operations."""
    
    def __init__(self, connection: AS400ConnectionManager):
        self.conn = connection
    
    def table_exists(self, table_name: str, library: str) -> bool:
        """Check if table exists in specified library."""
        sql = """
            SELECT COUNT(*) 
            FROM QSYS2.SYSTABLES 
            WHERE SYSTEM_TABLE_NAME = ? 
            AND SYSTEM_TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        return row[0] > 0
    
    def get_table_info(self, table_name: str, library: str) -> TableInfo | None:
        """Get table information from system catalogs."""
        sql = """
            SELECT 
                t.SYSTEM_TABLE_NAME,
                t.SYSTEM_TABLE_SCHEMA,
                t.TABLE_TYPE,
                t.TABLE_TEXT,
                t.NUMBER_ROWS,
                t.CREATE_TIMESTAMP,
                t.LAST_ALTERED_TIMESTAMP,
                t.JOURNALED,
                t.JOURNAL_LIBRARY,
                t.JOURNAL_NAME
            FROM QSYS2.SYSTABLES t
            WHERE t.SYSTEM_TABLE_NAME = ?
            AND t.SYSTEM_TABLE_SCHEMA = ?
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        row = cursor.fetchone()
        cursor.close()
        
        if not row:
            return None
        
        return TableInfo(
            name=row[0],
            library=row[1],
            table_type=row[2],
            description=row[3],
            row_count=row[4],
            created=str(row[5]) if row[5] else None,
            last_altered=str(row[6]) if row[6] else None,
            journaled=row[7] == "YES" if row[7] else False,
            journal_library=row[8],
            journal_name=row[9],
        )
    
    def get_columns(self, table_name: str, library: str) -> list[dict[str, Any]]:
        """Get column information for a table."""
        sql = """
            SELECT 
                c.SYSTEM_COLUMN_NAME,
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.LENGTH,
                c.NUMERIC_SCALE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT,
                c.COLUMN_TEXT
            FROM QSYS2.SYSCOLUMNS c
            WHERE c.SYSTEM_TABLE_NAME = ?
            AND c.SYSTEM_TABLE_SCHEMA = ?
            ORDER BY c.ORDINAL_POSITION
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "system_name": row[0],
                "name": row[1],
                "type": row[2],
                "length": row[3],
                "scale": row[4],
                "nullable": row[5] == "YES",
                "default": row[6],
                "description": row[7],
            })
        cursor.close()
        return columns
    
    def create_table(self, config: TableConfig, dry_run: bool = False) -> str:
        """Create table from configuration."""
        ddl = config.to_sql_ddl()
        
        if dry_run:
            logger.info("DRY RUN - Would execute:")
            logger.info(ddl)
            return ddl
        
        # Execute DDL statements
        statements = [s.strip() for s in ddl.split(";") if s.strip()]
        
        for stmt in statements:
            if stmt.upper().startswith(("CREATE", "LABEL")):
                logger.debug(f"Executing: {stmt[:100]}...")
                cursor = self.conn.execute(stmt)
                cursor.close()
        
        # Create indexes if specified
        if config.indexes:
            for idx in config.indexes:
                idx_sql = self._build_index_sql(config, idx)
                logger.debug(f"Creating index: {idx_sql[:100]}...")
                cursor = self.conn.execute(idx_sql)
                cursor.close()
        
        self.conn.commit()
        logger.info(f"Created table {config.library}.{config.name}")
        
        return ddl
    
    def drop_table(self, table_name: str, library: str, cascade: bool = False) -> None:
        """Drop a table."""
        cascade_str = "CASCADE" if cascade else ""
        sql = f"DROP TABLE {library}.{table_name} {cascade_str}".strip()
        
        logger.debug(f"Executing: {sql}")
        cursor = self.conn.execute(sql)
        cursor.close()
        self.conn.commit()
        
        logger.info(f"Dropped table {library}.{table_name}")
    
    def drop_create_table(
        self, 
        config: TableConfig, 
        force: bool = False,
        dry_run: bool = False
    ) -> str:
        """Drop and recreate table."""
        if self.table_exists(config.name, config.library):
            if not force and not dry_run:
                raise ValueError(
                    f"Table {config.library}.{config.name} exists. "
                    "Use --force to drop and recreate."
                )
            
            if dry_run:
                logger.info(f"DRY RUN - Would drop table {config.library}.{config.name}")
            else:
                self.drop_table(config.name, config.library)
        
        return self.create_table(config, dry_run)
    
    def load_sql_file(self, sql_path: str) -> str:
        """Load SQL from file."""
        with open(sql_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def execute_sql_file(self, sql_path: str, dry_run: bool = False) -> list[str]:
        """Execute SQL statements from file."""
        sql_content = self.load_sql_file(sql_path)
        
        # Split into statements
        statements = self._split_sql_statements(sql_content)
        
        executed = []
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            
            if dry_run:
                logger.info(f"DRY RUN - Would execute: {stmt[:100]}...")
            else:
                logger.debug(f"Executing: {stmt[:100]}...")
                cursor = self.conn.execute(stmt)
                cursor.close()
            
            executed.append(stmt)
        
        if not dry_run:
            self.conn.commit()
        
        return executed
    
    def _build_index_sql(self, config: TableConfig, index_def: dict[str, Any]) -> str:
        """Build CREATE INDEX SQL."""
        idx_name = index_def.get("name", f"IDX_{config.name}_{index_def['columns'][0]}")
        unique = "UNIQUE " if index_def.get("unique") else ""
        columns = ", ".join(index_def["columns"])
        
        return (
            f"CREATE {unique}INDEX {config.library}.{idx_name} "
            f"ON {config.library}.{config.name} ({columns})"
        )
    
    def _split_sql_statements(self, sql: str) -> list[str]:
        """Split SQL content into individual statements."""
        # Remove comments
        sql = re.sub(r"--.*?\n", "\n", sql)
        sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
        
        # Split by semicolon
        statements = []
        current = []
        
        for line in sql.split("\n"):
            line = line.strip()
            if not line:
                continue
            
            current.append(line)
            if line.endswith(";"):
                statements.append(" ".join(current))
                current = []
        
        if current:
            statements.append(" ".join(current))
        
        return statements
    
    def list_tables(self, library: str, table_type: str | None = None) -> list[TableInfo]:
        """List tables in a library."""
        sql = """
            SELECT 
                SYSTEM_TABLE_NAME,
                SYSTEM_TABLE_SCHEMA,
                TABLE_TYPE,
                TABLE_TEXT,
                NUMBER_ROWS,
                CREATE_TIMESTAMP,
                LAST_ALTERED_TIMESTAMP,
                JOURNALED,
                JOURNAL_LIBRARY,
                JOURNAL_NAME
            FROM QSYS2.SYSTABLES
            WHERE SYSTEM_TABLE_SCHEMA = ?
        """
        params: list[Any] = [library.upper()]
        
        if table_type:
            sql += " AND TABLE_TYPE = ?"
            params.append(table_type.upper())
        
        sql += " ORDER BY SYSTEM_TABLE_NAME"
        
        cursor = self.conn.execute(sql, tuple(params))
        tables = []
        
        for row in cursor.fetchall():
            tables.append(TableInfo(
                name=row[0],
                library=row[1],
                table_type=row[2],
                description=row[3],
                row_count=row[4],
                created=str(row[5]) if row[5] else None,
                last_altered=str(row[6]) if row[6] else None,
                journaled=row[7] == "YES" if row[7] else False,
                journal_library=row[8],
                journal_name=row[9],
            ))
        
        cursor.close()
        return tables
