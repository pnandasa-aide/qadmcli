"""Mockup data operations for testing."""

import logging
import random
from typing import Any, Optional
from dataclasses import dataclass

from ..utils.data_generator import DataGenerator
from .connection import AS400ConnectionManager

logger = logging.getLogger("qadmcli")


class SchemaValidationError(Exception):
    """Raised when schema validation fails."""
    pass


@dataclass
class MockupConfig:
    """Configuration for mockup operations."""
    insert_ratio: int = 50
    update_ratio: int = 30
    delete_ratio: int = 20
    total_transactions: int = 1000
    batch_size: int = 100
    dry_run: bool = False


class MockupManager:
    """Manages mockup data generation and operations."""

    def __init__(self, connection: AS400ConnectionManager, schema_hints: Optional[dict[str, str]] = None,
                 schema_validation: Optional[dict[str, Any]] = None):
        self.conn = connection
        self.data_generator = DataGenerator()
        self.schema_hints = schema_hints or {}
        self.schema_validation = schema_validation or {}

    def validate_schema(self, table_name: str, library: str) -> list[str]:
        """Validate that actual table schema matches the input schema.

        Returns a list of validation errors. Empty list if validation passes.
        """
        if not self.schema_validation:
            return []

        errors = []
        db_columns = self._get_columns(table_name, library)
        db_col_map = {col['name'].upper(): col for col in db_columns}

        for col_name, expected in self.schema_validation.items():
            col_name_upper = col_name.upper()
            if col_name_upper not in db_col_map:
                errors.append(f"Column '{col_name}' not found in table {library}.{table_name}")
                continue

            db_col = db_col_map[col_name_upper]

            # Check data type
            if 'type' in expected:
                expected_type = expected['type'].upper()
                actual_type = db_col['type'].upper()
                # Allow some flexibility in type matching (e.g., VARCHAR vs CHAR)
                if expected_type != actual_type:
                    # Check if types are compatible
                    compatible_types = [
                        ('VARCHAR', 'CHAR'),
                        ('CHAR', 'VARCHAR'),
                        ('DECIMAL', 'NUMERIC'),
                        ('NUMERIC', 'DECIMAL'),
                    ]
                    is_compatible = any(
                        (expected_type == compat[0] and actual_type == compat[1]) or
                        (expected_type == compat[1] and actual_type == compat[0])
                        for compat in compatible_types
                    )
                    if not is_compatible:
                        errors.append(
                            f"Column '{col_name}' type mismatch: expected {expected['type']}, "
                            f"got {db_col['type']}"
                        )

            # Check length
            if 'length' in expected and expected['length'] is not None:
                if db_col['length'] != expected['length']:
                    errors.append(
                        f"Column '{col_name}' length mismatch: expected {expected['length']}, "
                        f"got {db_col['length']}"
                    )

            # Check scale for decimal/numeric
            if 'scale' in expected and expected['scale'] is not None:
                if db_col['scale'] != expected['scale']:
                    errors.append(
                        f"Column '{col_name}' scale mismatch: expected {expected['scale']}, "
                        f"got {db_col['scale']}"
                    )

            # Check nullable
            if 'nullable' in expected:
                expected_nullable = expected['nullable']
                actual_nullable = db_col['nullable']
                if expected_nullable != actual_nullable:
                    errors.append(
                        f"Column '{col_name}' nullable mismatch: expected {expected_nullable}, "
                        f"got {actual_nullable}"
                    )

        return errors

    def generate_mock_data(self, table_name: str, library: str,
                          config: MockupConfig) -> dict[str, Any]:
        """Generate mock data for a table."""
        # Store table info for batch execution
        self._table_name = table_name
        self._library = library
        
        # Validate schema if validation rules are provided
        if self.schema_validation:
            validation_errors = self.validate_schema(table_name, library)
            if validation_errors:
                error_msg = "Schema validation failed:\n" + "\n".join(f"  - {e}" for e in validation_errors)
                raise SchemaValidationError(error_msg)

        # Get table columns
        columns = self._get_columns(table_name, library)
        
        # Get primary key info
        pk_columns = self._get_primary_key(table_name, library)
        
        # Get existing PK values to avoid duplicates
        existing_pks = self._get_existing_pk_values(table_name, library, pk_columns) if pk_columns else set()
        
        results = {
            "inserts": [],
            "updates": [],
            "deletes": [],
            "sql_statements": [],
            "stats": {"inserted": 0, "updated": 0, "deleted": 0}
        }
        
        # Calculate transaction counts
        total = config.total_transactions
        insert_count = int(total * config.insert_ratio / 100)
        update_count = int(total * config.update_ratio / 100)
        delete_count = int(total * config.delete_ratio / 100)
        
        logger.info(f"Generating {insert_count} inserts, {update_count} updates, {delete_count} deletes")
        
        # Generate INSERT operations
        for i in range(insert_count):
            row_data = self._generate_row(columns, pk_columns, existing_pks, is_insert=True)
            sql = self._build_insert_sql(table_name, library, row_data)
            
            if config.dry_run:
                results["sql_statements"].append(sql)
            else:
                results["inserts"].append(row_data)
            
            # Execute in batches
            if not config.dry_run and (i + 1) % config.batch_size == 0:
                self._execute_batch(results["inserts"], "INSERT")
                results["stats"]["inserted"] += len(results["inserts"])
                results["inserts"] = []
                logger.debug(f"Executed batch of {config.batch_size} inserts")
        
        # Execute remaining inserts
        if not config.dry_run and results["inserts"]:
            self._execute_batch(results["inserts"], "INSERT")
            results["stats"]["inserted"] += len(results["inserts"])
        
        # Get row IDs for updates/deletes (now returns list of lists for composite key support)
        row_ids = self._get_random_row_ids(table_name, library, update_count + delete_count)
        
        # Generate UPDATE operations
        for i in range(min(update_count, len(row_ids))):
            pk_values = row_ids[i]  # List of PK values for composite keys
            update_data = self._generate_update_data(columns, pk_columns)
            sql = self._build_update_sql(table_name, library, update_data, pk_columns, pk_values)
            
            if config.dry_run:
                results["sql_statements"].append(sql)
            else:
                results["updates"].append({"pk_values": pk_values, "data": update_data})
            
            if not config.dry_run and (i + 1) % config.batch_size == 0:
                self._execute_batch(results["updates"], "UPDATE", pk_columns)
                results["stats"]["updated"] += len(results["updates"])
                results["updates"] = []
        
        if not config.dry_run and results["updates"]:
            self._execute_batch(results["updates"], "UPDATE", pk_columns)
            results["stats"]["updated"] += len(results["updates"])
        
        # Generate DELETE operations
        delete_ids = row_ids[update_count:update_count + delete_count]
        for i, pk_values in enumerate(delete_ids):
            sql = self._build_delete_sql(table_name, library, pk_columns, pk_values)
            
            if config.dry_run:
                results["sql_statements"].append(sql)
            else:
                results["deletes"].append(pk_values)
            
            if not config.dry_run and (i + 1) % config.batch_size == 0:
                self._execute_batch(results["deletes"], "DELETE", pk_columns)
                results["stats"]["deleted"] += len(results["deletes"])
                results["deletes"] = []
        
        if not config.dry_run and results["deletes"]:
            self._execute_batch(results["deletes"], "DELETE", pk_columns)
            results["stats"]["deleted"] += len(results["deletes"])
        
        return results
    
    def _get_columns(self, table_name: str, library: str) -> list[dict[str, Any]]:
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
                c.COLUMN_TEXT,
                c.IS_IDENTITY
            FROM QSYS2.SYSCOLUMNS c
            WHERE c.SYSTEM_TABLE_NAME = ?
            AND c.SYSTEM_TABLE_SCHEMA = ?
            ORDER BY c.ORDINAL_POSITION
        """
        cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
        columns = []
        for row in cursor.fetchall():
            description = str(row[7]) if row[7] else None
            logger.debug(f"Column {row[1]} description: {description}")
            # Extract hint from description if present (format: "Description [hint:xxx]")
            hint = None
            if description and "[hint:" in description.lower():
                import re
                hint_match = re.search(r'\[hint:([^\]]+)\]', description, re.IGNORECASE)
                if hint_match:
                    hint = hint_match.group(1).strip()
                    logger.debug(f"Extracted hint '{hint}' from description")
                    # Remove hint from description
                    description = re.sub(r'\[hint:[^\]]+\]', '', description, flags=re.IGNORECASE).strip()

            col_name = str(row[1])
            # Merge schema hints with database hints (schema hints take priority)
            final_hint = hint
            if col_name.upper() in self.schema_hints:
                final_hint = self.schema_hints[col_name.upper()]
                logger.debug(f"Using schema hint '{final_hint}' for column {col_name}")

            # Check if column is identity or generated
            is_identity = row[8] == "YES" if row[8] else False
            column_default = str(row[6]) if row[6] else ""
            is_generated = "GENERATED" in column_default.upper()

            columns.append({
                "system_name": str(row[0]),
                "name": col_name,
                "type": str(row[2]),
                "length": row[3],
                "scale": row[4],
                "nullable": row[5] == "YES",
                "default": row[6],
                "description": description,
                "hint": final_hint,
                "is_identity": is_identity,
                "is_generated": is_generated,
            })
        cursor.close()
        return columns
    
    def _get_primary_key(self, table_name: str, library: str) -> list[str]:
        """Get primary key columns."""
        # Use SYSKEYCST for accurate PK column info - simpler query without JOIN
        sql = """
            SELECT COLUMN_NAME
            FROM QSYS2.SYSKEYCST
            WHERE SYSTEM_TABLE_NAME = ?
            AND SYSTEM_TABLE_SCHEMA = ?
            ORDER BY ORDINAL_POSITION
        """
        try:
            cursor = self.conn.execute(sql, (table_name.upper(), library.upper()))
            pk_columns = [str(row[0]) for row in cursor.fetchall()]
            cursor.close()
            return pk_columns
        except Exception as e:
            logger.warning(f"Could not get primary key: {e}")
            return []
    
    def _get_existing_pk_values(self, table_name: str, library: str,
                                pk_columns: list[str]) -> set:
        """Get existing primary key values to avoid duplicates.
            
        For large tables, this returns an empty set to avoid performance issues.
        PK uniqueness will be handled by catching duplicate key errors.
        """
        if not pk_columns:
            return set()
            
        # Skip fetching all PK values for large tables - too slow
        # Instead, we'll handle duplicates by catching SQL errors
        logger.debug("Skipping full PK value fetch for performance - will handle duplicates via error handling")
        return set()
        
    def _get_random_row_ids(self, table_name: str, library: str,
                           count: int) -> list[list[Any]]:
        """Get random row IDs for updates/deletes using efficient sampling.
        
        Returns list of lists, where each inner list contains values for all PK columns.
        Supports composite primary keys.
        """
        # Get primary key columns
        pk_columns = self._get_primary_key(table_name, library)
        if not pk_columns:
            logger.warning("No primary key found for random row selection")
            return []
        
        # Build column list for SELECT
        pk_cols_str = ", ".join(pk_columns)
            
        # Use TABLESAMPLE for efficient random sampling on large tables
        sql = f"""
            SELECT {pk_cols_str} FROM {library}.{table_name}
            TABLESAMPLE SYSTEM(0.01)
            FETCH FIRST {count * 10} ROWS ONLY
        """
        try:
            cursor = self.conn.execute(sql)
            rows = [list(row) for row in cursor.fetchall()]  # Get all PK column values
            cursor.close()
                
            # Randomly sample from the results
            if len(rows) >= count:
                import random
                return random.sample(rows, count)
            elif rows:
                return rows
        except Exception as e:
            logger.debug(f"TABLESAMPLE failed: {e}, trying alternative")
            
        # Alternative: Use RAND() with WHERE clause for better performance
        try:
            sql = f"""
                SELECT {pk_cols_str} FROM {library}.{table_name}
                WHERE RAND() < 0.001
                FETCH FIRST {count} ROWS ONLY
            """
            cursor = self.conn.execute(sql)
            rows = [list(row) for row in cursor.fetchall()]
            cursor.close()
            if rows:
                return rows
        except Exception as e:
            logger.debug(f"RAND() with WHERE failed: {e}")
            
        # For single-column PK: Final fallback using MIN/MAX range
        if len(pk_columns) == 1:
            try:
                pk_col = pk_columns[0]
                sql = f"SELECT MIN({pk_col}), MAX({pk_col}) FROM {library}.{table_name}"
                cursor = self.conn.execute(sql)
                row = cursor.fetchone()
                cursor.close()
                    
                if row and row[0] is not None and row[1] is not None:
                    min_id, max_id = row[0], row[1]
                    import random
                    random_ids = [random.randint(min_id, max_id) for _ in range(count * 2)]
                    id_list = ",".join(str(id_val) for id_val in random_ids)
                    verify_sql = f"SELECT {pk_col} FROM {library}.{table_name} WHERE {pk_col} IN ({id_list}) FETCH FIRST {count} ROWS ONLY"
                    cursor = self.conn.execute(verify_sql)
                    existing_ids = [[row[0]] for row in cursor.fetchall()]  # Return as list of lists
                    cursor.close()
                    return existing_ids[:count]
            except Exception as e:
                logger.warning(f"MIN/MAX fallback failed: {e}")
            
        return []
    
    def _generate_row(self, columns: list[dict], pk_columns: list[str],
                     existing_pks: set, is_insert: bool = True) -> dict[str, Any]:
        """Generate a row of data."""
        row = {}

        for col in columns:
            col_name = col["name"]

            # Skip identity or generated columns (for INSERTs)
            if is_insert and (col.get("is_identity") or col.get("is_generated")):
                logger.debug(f"Skipping identity/generated column {col_name}")
                continue

            # Skip if column has default value
            if col["default"]:
                continue

            # Generate PK with uniqueness check
            if col_name in pk_columns and is_insert:
                value = self._generate_unique_pk(col, existing_pks)
                existing_pks.add(value)
            else:
                # Pass hint if available
                hint = col.get("hint")
                if hint:
                    logger.debug(f"Using hint '{hint}' for column {col_name}")
                value = self.data_generator.generate_for_column(
                    col_name, col["type"], col["length"], col["scale"], hint
                )

            row[col_name] = value

        return row
    
    def _generate_unique_pk(self, col: dict, existing_pks: set) -> Any:
        """Generate a unique primary key value."""
        max_attempts = 1000
        for _ in range(max_attempts):
            value = self.data_generator.generate_for_column(
                col["name"], col["type"], col["length"], col["scale"], col.get("hint")
            )
            if value not in existing_pks:
                return value
        
        # If we can't find a unique value, add timestamp
        import time
        base_value = self.data_generator.generate_for_column(
            col["name"], col["type"], col["length"], col["scale"], col.get("hint")
        )
        return f"{base_value}_{int(time.time() * 1000)}"
    
    def _generate_update_data(self, columns: list[dict],
                             pk_columns: list[str]) -> dict[str, Any]:
        """Generate data for update (excluding PK columns)."""
        update_data = {}

        # Select random columns to update (excluding PK)
        updatable_cols = [c for c in columns if c["name"] not in pk_columns]
        if not updatable_cols:
            return update_data

        # Update 1-3 random columns
        num_cols = min(random.randint(1, 3), len(updatable_cols))
        cols_to_update = random.sample(updatable_cols, num_cols)

        for col in cols_to_update:
            # Pass hint if available for consistent data generation
            value = self.data_generator.generate_for_column(
                col["name"], col["type"], col["length"], col["scale"], col.get("hint")
            )
            update_data[col["name"]] = value

        return update_data
    
    def _build_insert_sql(self, table_name: str, library: str, 
                         row_data: dict) -> str:
        """Build INSERT SQL statement."""
        columns = ", ".join(row_data.keys())
        values = []
        
        for val in row_data.values():
            if val is None:
                values.append("NULL")
            elif isinstance(val, str):
                escaped = val.replace("'", "''")
                values.append(f"'{escaped}'")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            else:
                values.append(f"'{str(val)}'")
        
        values_str = ", ".join(values)
        return f"INSERT INTO {library}.{table_name} ({columns}) VALUES ({values_str});"
    
    def _build_update_sql(self, table_name: str, library: str,
                         update_data: dict, pk_columns: list[str],
                         pk_values: list[Any]) -> str:
        """Build UPDATE SQL statement.
        
        Supports composite primary keys by using all PK columns in WHERE clause.
        """
        if not update_data:
            return ""
        
        set_clauses = []
        for col, val in update_data.items():
            if val is None:
                set_clauses.append(f"{col} = NULL")
            elif isinstance(val, str):
                escaped = val.replace("'", "''")
                set_clauses.append(f"{col} = '{escaped}'")
            elif isinstance(val, (int, float)):
                set_clauses.append(f"{col} = {val}")
            else:
                set_clauses.append(f"{col} = '{str(val)}'")
        
        set_str = ", ".join(set_clauses)
        
        # Build WHERE clause with all PK columns (composite key support)
        if pk_columns and pk_values and len(pk_columns) == len(pk_values):
            where_conditions = []
            for col, val in zip(pk_columns, pk_values):
                if isinstance(val, str):
                    escaped_val = val.replace("'", "''")
                    where_conditions.append(f"{col} = '{escaped_val}'")
                else:
                    where_conditions.append(f"{col} = {val}")
            where = " AND ".join(where_conditions)
        elif pk_columns:
            # Fallback to first column only
            where = f"{pk_columns[0]} = {pk_values[0] if pk_values else 0}"
        else:
            where = "1=0"  # Safety: prevent update without PK
        
        return f"UPDATE {library}.{table_name} SET {set_str} WHERE {where};"
    
    def _build_delete_sql(self, table_name: str, library: str,
                         pk_columns: list[str], pk_values: list[Any]) -> str:
        """Build DELETE SQL statement.
        
        Supports composite primary keys by using all PK columns in WHERE clause.
        """
        # Build WHERE clause with all PK columns (composite key support)
        if pk_columns and pk_values and len(pk_columns) == len(pk_values):
            where_conditions = []
            for col, val in zip(pk_columns, pk_values):
                if isinstance(val, str):
                    escaped_val = val.replace("'", "''")
                    where_conditions.append(f"{col} = '{escaped_val}'")
                else:
                    where_conditions.append(f"{col} = {val}")
            where = " AND ".join(where_conditions)
        elif pk_columns:
            # Fallback to first column only
            where = f"{pk_columns[0]} = {pk_values[0] if pk_values else 0}"
        else:
            where = "1=0"  # Safety: prevent delete without PK
        
        return f"DELETE FROM {library}.{table_name} WHERE {where};"
    
    def _execute_batch(self, batch: list, operation: str,
                      pk_columns: Optional[list[str]] = None):
        """Execute a batch of operations."""
        if not batch:
            return
            
        # Get stored table info
        table_name = getattr(self, '_table_name', '')
        library = getattr(self, '_library', '')
            
        try:
            if operation == "INSERT":
                for row_data in batch:
                    sql = self._build_insert_sql(table_name, library, row_data)
                    cursor = self.conn.execute(sql.rstrip(';'))
                    cursor.close()
                
            elif operation == "UPDATE":
                for item in batch:
                    pk_values = item["pk_values"]
                    update_data = item["data"]
                    if update_data:
                        sql = self._build_update_sql(table_name, library, update_data, pk_columns or [], pk_values)
                        cursor = self.conn.execute(sql.rstrip(';'))
                        cursor.close()
                
            elif operation == "DELETE":
                for pk_values in batch:
                    sql = self._build_delete_sql(table_name, library, pk_columns or [], pk_values)
                    cursor = self.conn.execute(sql.rstrip(';'))
                    cursor.close()
                
            self.conn.commit()
            logger.debug(f"Executed batch of {len(batch)} {operation} operations")
            
        except Exception as e:
            logger.error(f"Error executing batch {operation}: {e}")
            raise
