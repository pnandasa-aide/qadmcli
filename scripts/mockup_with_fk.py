#!/usr/bin/env python3
"""
Mockup data generator with foreign key support.

This script manages FK relationships by:
1. Defining table schemas with hints and FK relationships
2. Processing tables in dependency order
3. Using qadmcli mockup for parent tables (no FK constraints)
4. Using FK-aware SQL generation for child tables (with FK constraints)
"""

import os
import subprocess
import json
import random
import sys
import yaml
from datetime import datetime, date
from typing import Any, Optional, Callable
from dataclasses import dataclass, field, asdict


@dataclass
class ColumnDef:
    """Column definition with type, generation hint, and FK reference."""
    name: str
    col_type: str = "string"  # string, int, decimal, date, timestamp
    nullable: bool = True
    is_pk: bool = False
    is_identity: bool = False
    # FK reference: {"table": "PARENT_TABLE", "column": "PARENT_PK"}
    fk_ref: Optional[dict[str, str]] = None
    # Generator: static value, lambda, or None (auto-generate)
    generator: Any = None
    # For strings: max length
    length: Optional[int] = None


@dataclass
class TableDef:
    """Table definition with columns and processing hints."""
    name: str
    library: str
    columns: list[ColumnDef] = field(default_factory=list)
    # Processing strategy:
    # - "mockup": Use qadmcli mockup (for tables without FK constraints)
    # - "sql_fk": Use FK-aware SQL generation (for tables with FKs)
    strategy: str = "mockup"
    # Row count for generation
    row_count: int = 10
    # Tables this table depends on (for ordering)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class TableSequence:
    """Defines the order and dependencies for mockup generation."""
    name: str
    library: str
    depends_on: list[str] = field(default_factory=list)
    fk_columns: dict[str, str] = field(default_factory=dict)  # column -> parent_table


class SchemaRegistry:
    """Registry for table schema definitions with FK relationships."""
    
    def __init__(self):
        self.tables: dict[str, TableDef] = {}
    
    def register(self, table_def: TableDef):
        """Register a table definition."""
        self.tables[table_def.name.upper()] = table_def
    
    def get(self, table_name: str) -> Optional[TableDef]:
        """Get table definition by name."""
        return self.tables.get(table_name.upper())
    
    def get_processing_order(self, include_reference: bool = False) -> list[str]:
        """Get tables in dependency order (topological sort).
        
        Args:
            include_reference: If True, include reference-only tables in output
        """
        visited = set()
        order = []
        
        def visit(table_name: str, path: set):
            if table_name in path:
                raise ValueError(f"Circular dependency detected: {' -> '.join(path)} -> {table_name}")
            if table_name in visited:
                return
            
            table_def = self.get(table_name)
            if table_def:
                path.add(table_name)
                for dep in table_def.depends_on:
                    visit(dep, path)
                path.remove(table_name)
                
                # Skip reference tables unless explicitly included
                if table_def.strategy == "reference" and not include_reference:
                    visited.add(table_name)
                    return
            
            visited.add(table_name)
            order.append(table_name)
        
        for name in self.tables:
            visit(name, set())
        
        return order
    
    def get_fk_columns(self, table_name: str) -> dict[str, dict[str, str]]:
        """Get FK column mappings for a table."""
        table_def = self.get(table_name)
        if not table_def:
            return {}
        
        fk_map = {}
        for col in table_def.columns:
            if col.fk_ref:
                fk_map[col.name] = col.fk_ref
        return fk_map
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> "SchemaRegistry":
        """Load schema registry from YAML file."""
        registry = cls()
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        library = data.get('library', 'GSLIBTST')
        
        for table_data in data.get('tables', []):
            columns = []
            for col_data in table_data.get('columns', []):
                # Parse generator string to function
                generator = col_data.get('generator')
                if isinstance(generator, str):
                    generator = cls._parse_generator(generator)
                
                col = ColumnDef(
                    name=col_data['name'],
                    col_type=col_data.get('type', 'string'),
                    nullable=col_data.get('nullable', True),
                    is_pk=col_data.get('is_pk', False),
                    is_identity=col_data.get('is_identity', False),
                    fk_ref=col_data.get('fk_ref'),
                    generator=generator,
                    length=col_data.get('length')
                )
                columns.append(col)
            
            table_def = TableDef(
                name=table_data['name'],
                library=table_data.get('library', library),
                columns=columns,
                strategy=table_data.get('strategy', 'mockup'),
                row_count=table_data.get('row_count', 10),
                depends_on=table_data.get('depends_on', [])
            )
            registry.register(table_def)
        
        return registry
    
    @staticmethod
    def _parse_generator(gen_str: str):
        """Parse generator string to callable function."""
        gen_str = gen_str.strip()
        
        # today() - current date
        if gen_str == "today()":
            return lambda: datetime.now().strftime('%Y-%m-%d')
        
        # today_plus_years(n) - current date + n years
        if gen_str.startswith("today_plus_years("):
            n = int(gen_str[17:-1])
            return lambda years=n: (datetime.now().replace(year=datetime.now().year + years)).strftime('%Y-%m-%d')
        
        # now() - current timestamp
        if gen_str == "now()":
            return lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # random_int(min, max)
        if gen_str.startswith("random_int("):
            args = gen_str[11:-1].split(',')
            min_val = int(args[0].strip())
            max_val = int(args[1].strip())
            return lambda min_v=min_val, max_v=max_val: random.randint(min_v, max_v)
        
        # random_decimal(min, max, scale)
        if gen_str.startswith("random_decimal("):
            args = gen_str[15:-1].split(',')
            min_val = float(args[0].strip())
            max_val = float(args[1].strip())
            scale = int(args[2].strip())
            return lambda min_v=min_val, max_v=max_val, sc=scale: round(random.uniform(min_v, max_v), sc)
        
        # random_choice([...])
        if gen_str.startswith("random_choice("):
            choices_str = gen_str[14:-1]
            # Parse list like "['a', 'b', 'c']"
            choices = eval(choices_str)
            return lambda ch=choices: random.choice(ch)
        
        # random_text(prefix, min, max, suffix)
        if gen_str.startswith("random_text("):
            args = gen_str[12:-1].split(',')
            prefix = args[0].strip().strip("'\"")
            min_val = int(args[1].strip())
            max_val = int(args[2].strip())
            suffix = args[3].strip().strip("'\"") if len(args) > 3 else ""
            return lambda p=prefix, min_v=min_val, max_v=max_val, s=suffix: f"{p}{random.randint(min_v, max_v)}{s}"
        
        # PROD{random_int(...)} - template with embedded generator
        if "{random_int(" in gen_str:
            def make_template_fn(template):
                import re
                pattern = r'\{random_int\((\d+),\s*(\d+)\)\}'
                match = re.search(pattern, template)
                if match:
                    min_v, max_v = int(match.group(1)), int(match.group(2))
                    prefix = template[:match.start()]
                    suffix = template[match.end():]
                    return lambda: f"{prefix}{random.randint(min_v, max_v)}{suffix}"
                return lambda: template
            return make_template_fn(gen_str)
        
        # Default: return as static string
        return lambda val=gen_str: val
    
    @classmethod
    def from_database(cls, library: str, table_names: Optional[list[str]] = None,
                      conn_manager: Optional[Any] = None) -> "SchemaRegistry":
        """Auto-detect schema from DB2 system tables.
        
        Args:
            library: Library/schema name to introspect
            table_names: Optional list of specific tables, or None for all tables
            conn_manager: Optional connection manager to use for queries
        
        Returns:
            SchemaRegistry populated with detected schema
        """
        registry = cls()
        
        # Query to get all tables in library
        tables_sql = """
            SELECT SYSTEM_TABLE_NAME, TABLE_NAME, TABLE_TYPE
            FROM QSYS2.SYSTABLES
            WHERE SYSTEM_TABLE_SCHEMA = ?
        """
        if table_names:
            placeholders = ','.join(['?' for _ in table_names])
            tables_sql += f" AND SYSTEM_TABLE_NAME IN ({placeholders})"
        
        # This would need actual DB connection to execute
        # For now, return empty registry with instructions
        print(f"# Auto-detect schema from database: {library}")
        print("# To use auto-detection, provide a connection manager:")
        print("#   registry = SchemaRegistry.from_database('GSLIBTST', conn_manager=conn)")
        print("#")
        print("# Tables that would be detected:")
        if table_names:
            for name in table_names:
                print(f"#   - {name}")
        else:
            print("#   (all tables in library)")
        
        return registry
    
    @classmethod
    def create_insurance_schema(cls, library: str = "GSLIBTST") -> "SchemaRegistry":
        """Create the insurance tables schema."""
        registry = cls()
        
        # CUSTOMERS - reference-only table (pre-existing, not generated)
        # Included in registry so FK references can be resolved
        registry.register(TableDef(
            name="CUSTOMERS",
            library=library,
            columns=[
                ColumnDef("CUST_ID", "int", is_pk=True),
                ColumnDef("FIRST_NAME", "string", length=50),
                ColumnDef("LAST_NAME", "string", length=50),
                ColumnDef("EMAIL", "string", length=100),
            ],
            strategy="reference",  # Special strategy - don't generate, just reference
            row_count=0,
            depends_on=[]
        ))
        
        # INSURANCE_PRODUCTS - parent table, use mockup
        registry.register(TableDef(
            name="INSURANCE_PRODUCTS",
            library=library,
            columns=[
                ColumnDef("PRODUCT_ID", "int", is_pk=True, is_identity=True),
                ColumnDef("PRODUCT_CODE", "string", length=20, generator=lambda: f"PROD{random.randint(1000, 9999)}"),
                ColumnDef("PRODUCT_NAME", "string", length=100, generator=lambda: random.choice(["Life Insurance", "Health Insurance", "Car Insurance", "Home Insurance"])),
                ColumnDef("PRODUCT_TYPE", "string", length=20, generator=lambda: random.choice(["LIFE", "HEALTH", "AUTO", "PROPERTY"])),
                ColumnDef("BASE_PREMIUM", "decimal", generator=lambda: round(random.uniform(100, 1000), 2)),
                ColumnDef("STATUS", "string", length=10, generator=lambda: random.choice(["ACTIVE", "INACTIVE"])),
            ],
            strategy="mockup",
            row_count=10
        ))
        
        # SUBSCRIPTIONS - child table with FKs, use sql_fk
        registry.register(TableDef(
            name="SUBSCRIPTIONS",
            library=library,
            columns=[
                ColumnDef("SUBSCRIPTION_ID", "int", is_pk=True, is_identity=True),
                ColumnDef("CUST_ID", "int", fk_ref={"table": "CUSTOMERS", "column": "CUST_ID"}),
                ColumnDef("PRODUCT_ID", "int", fk_ref={"table": "INSURANCE_PRODUCTS", "column": "PRODUCT_ID"}),
                ColumnDef("START_DATE", "date", generator=lambda: datetime.now().strftime('%Y-%m-%d')),
                ColumnDef("END_DATE", "date", generator=lambda: (datetime.now().replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d')),
                ColumnDef("PREMIUM_AMOUNT", "decimal", generator=lambda: round(random.uniform(500, 5000), 2)),
                ColumnDef("STATUS", "string", length=20, generator=lambda: random.choice(["ACTIVE", "PENDING", "SUSPENDED"])),
            ],
            strategy="sql_fk",
            row_count=20,
            depends_on=["INSURANCE_PRODUCTS", "CUSTOMERS"]
        ))
        
        # PAYMENTS - child table with FK
        registry.register(TableDef(
            name="PAYMENTS",
            library=library,
            columns=[
                ColumnDef("PAYMENT_ID", "int", is_pk=True, is_identity=True),
                ColumnDef("SUBSCRIPTION_ID", "int", fk_ref={"table": "SUBSCRIPTIONS", "column": "SUBSCRIPTION_ID"}),
                ColumnDef("PAYMENT_DATE", "date", generator=lambda: datetime.now().strftime('%Y-%m-%d')),
                ColumnDef("AMOUNT", "decimal", generator=lambda: round(random.uniform(100, 1000), 2)),
                ColumnDef("PAYMENT_METHOD", "string", length=20, generator=lambda: random.choice(["CASH", "CREDIT", "DEBIT", "BANK_TRANSFER"])),
                ColumnDef("STATUS", "string", length=20, generator=lambda: random.choice(["PAID", "PENDING", "FAILED"])),
            ],
            strategy="sql_fk",
            row_count=50,
            depends_on=["SUBSCRIPTIONS"]
        ))
        
        # CLAIMS - child table with FK
        registry.register(TableDef(
            name="CLAIMS",
            library=library,
            columns=[
                ColumnDef("CLAIM_ID", "int", is_pk=True, is_identity=True),
                ColumnDef("SUBSCRIPTION_ID", "int", fk_ref={"table": "SUBSCRIPTIONS", "column": "SUBSCRIPTION_ID"}),
                ColumnDef("CLAIM_DATE", "date", generator=lambda: datetime.now().strftime('%Y-%m-%d')),
                ColumnDef("CLAIM_AMOUNT", "decimal", generator=lambda: round(random.uniform(1000, 50000), 2)),
                ColumnDef("CLAIM_TYPE", "string", length=30, generator=lambda: random.choice(["MEDICAL", "ACCIDENT", "PROPERTY_DAMAGE", "THEFT"])),
                ColumnDef("STATUS", "string", length=20, generator=lambda: random.choice(["PENDING", "APPROVED", "REJECTED", "PROCESSING"])),
                ColumnDef("DESCRIPTION", "string", length=500, generator=lambda: f"Claim description {random.randint(1, 9999)}"),
            ],
            strategy="sql_fk",
            row_count=15,
            depends_on=["SUBSCRIPTIONS"]
        ))
        
        # CLAIM_DOCUMENTS - child table with FK
        registry.register(TableDef(
            name="CLAIM_DOCUMENTS",
            library=library,
            columns=[
                ColumnDef("DOCUMENT_ID", "int", is_pk=True, is_identity=True),
                ColumnDef("CLAIM_ID", "int", fk_ref={"table": "CLAIMS", "column": "CLAIM_ID"}),
                ColumnDef("DOCUMENT_TYPE", "string", length=30, generator=lambda: random.choice(["RECEIPT", "INVOICE", "REPORT", "PHOTO", "CERTIFICATE"])),
                ColumnDef("FILE_PATH", "string", length=255, generator=lambda: f"/docs/claim_{random.randint(1000, 9999)}.pdf"),
                ColumnDef("UPLOAD_DATE", "timestamp", generator=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            ],
            strategy="sql_fk",
            row_count=30,
            depends_on=["CLAIMS"]
        ))
        
        return registry


class MockQadmCLI:
    """Simulates qadmcli responses for demo/testing without actual database."""
    
    def __init__(self, registry: Optional[SchemaRegistry] = None):
        self.registry = registry
        self.simulated_data: dict[str, list[int]] = {
            "CUSTOMERS": list(range(1001, 1021)),  # 20 existing customers
        }
        # Initialize empty lists for registry tables
        if registry:
            for table_name in registry.tables:
                if table_name not in self.simulated_data:
                    self.simulated_data[table_name] = []
        else:
            self.simulated_data.update({
                "INSURANCE_PRODUCTS": [],
                "SUBSCRIPTIONS": [],
                "PAYMENTS": [],
                "CLAIMS": [],
                "CLAIM_DOCUMENTS": []
            })
        
        self.next_ids = {
            "PRODUCT_ID": 100,
            "SUBSCRIPTION_ID": 1000,
            "PAYMENT_ID": 5000,
            "CLAIM_ID": 2000,
            "DOCUMENT_ID": 10000
        }
    
    def query(self, sql: str, format_type: str = "json") -> str:
        """Simulate SQL query response."""
        # Parse table name from SQL
        sql_upper = sql.upper()
        for table in self.simulated_data:
            if table in sql_upper:
                ids = self.simulated_data[table]
                if format_type == "json":
                    # Find ID column name
                    id_col = None
                    if "CUST_ID" in sql_upper:
                        id_col = "CUST_ID"
                    elif "PRODUCT_ID" in sql_upper:
                        id_col = "PRODUCT_ID"
                    elif "SUBSCRIPTION_ID" in sql_upper:
                        id_col = "SUBSCRIPTION_ID"
                    elif "PAYMENT_ID" in sql_upper:
                        id_col = "PAYMENT_ID"
                    elif "CLAIM_ID" in sql_upper:
                        id_col = "CLAIM_ID"
                    elif "DOCUMENT_ID" in sql_upper:
                        id_col = "DOCUMENT_ID"
                    
                    if id_col:
                        rows = [{id_col: id_val} for id_val in ids[:100]]
                        return json.dumps(rows)
                return "[]"
        return "[]"
    
    def mockup_generate(self, table: str, library: str, insert: int, update: int, 
                       delete: int, total: int, dry_run: bool = False) -> dict:
        """Simulate mockup generate response."""
        result = {
            "success": True,
            "table": table,
            "operations": [],
            "generated_ids": [],
            "stdout": "",
            "stderr": "",
            "returncode": 0
        }
        
        # Determine ID column for this table
        id_map = {
            "INSURANCE_PRODUCTS": "PRODUCT_ID",
            "SUBSCRIPTIONS": "SUBSCRIPTION_ID",
            "PAYMENTS": "PAYMENT_ID",
            "CLAIMS": "CLAIM_ID",
            "CLAIM_DOCUMENTS": "DOCUMENT_ID"
        }
        id_col = id_map.get(table)
        
        if dry_run:
            # Generate simulated SQL statements
            sql_statements = []
            generated_ids = []
            for i in range(insert):
                if id_col:
                    new_id = self.next_ids.get(id_col, 100) + i
                    generated_ids.append(new_id)
                    if table == "INSURANCE_PRODUCTS":
                        sql_statements.append(
                            f"INSERT INTO {library}.{table} (PRODUCT_ID, PRODUCT_NAME, PRODUCT_TYPE, ...) "
                            f"VALUES ({new_id}, 'Product_{new_id}', 'LIFE', ...);"
                        )
                    elif table == "SUBSCRIPTIONS":
                        # For dry-run, show that FK values would be needed
                        sql_statements.append(
                            f"INSERT INTO {library}.{table} (SUBSCRIPTION_ID, CUST_ID, PRODUCT_ID, ...) "
                            f"VALUES ({new_id}, <FK:CUST_ID>, <FK:PRODUCT_ID>, ...);"
                        )
                    else:
                        sql_statements.append(
                            f"INSERT INTO {library}.{table} ({id_col}, ...) VALUES ({new_id}, ...);"
                        )
            
            result["stdout"] = f"[DRY-RUN] Would execute {insert} INSERTs, {update} UPDATEs, {delete} DELETEs\n"
            result["stdout"] += "Sample SQL statements:\n" + "\n".join(sql_statements[:3])
            if len(sql_statements) > 3:
                result["stdout"] += f"\n... and {len(sql_statements) - 3} more"
            result["operations"] = sql_statements
            result["generated_ids"] = generated_ids
            
        else:
            # Simulate actual execution - generate IDs
            generated = []
            for i in range(insert):
                if id_col:
                    new_id = self.next_ids[id_col]
                    self.next_ids[id_col] += 1
                    generated.append(new_id)
            
            self.simulated_data[table] = generated
            result["generated_ids"] = generated
            result["stdout"] = f"Inserted {insert} rows into {library}.{table}"
            result["operations"] = [{"type": "INSERT", "id": gid} for gid in generated]
        
        return result


class MockupFKManager:
    """Manages mockup generation with foreign key support."""
    
    def __init__(self, library: str = "GSLIBTST", demo_mode: bool = False, 
                 registry: Optional[SchemaRegistry] = None):
        self.library = library
        self.generated_ids: dict[str, list[int]] = {}  # table_name -> list of IDs
        self.failed_tables: list[str] = []
        self.demo_mode = demo_mode
        self.registry = registry or SchemaRegistry.create_insurance_schema(library)
        self.mock_cli = MockQadmCLI(self.registry) if demo_mode else None
        
    def get_existing_ids(self, table: str, id_column: str) -> list[int]:
        """Query existing IDs from a table."""
        if self.demo_mode and self.mock_cli:
            # Use mock data in demo mode
            result = self.mock_cli.query(f"SELECT {id_column} FROM {self.library}.{table}", "json")
            try:
                data = json.loads(result)
                return [row[id_column.upper()] for row in data if id_column.upper() in row]
            except:
                return []
        
        try:
            result = subprocess.run(
                ["qadmcli", "sql", "query", "-q", 
                 f"SELECT {id_column} FROM {self.library}.{table} FETCH FIRST 1000 ROWS ONLY",
                 "--format", "json"],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse JSON output
            lines = [line for line in result.stdout.split('\n') if line.strip().startswith('[')]
            if lines:
                data = json.loads(lines[0])
                ids = [row[id_column.upper()] for row in data if id_column.upper() in row]
                return ids
        except Exception as e:
            print(f"Warning: Could not fetch existing IDs from {table}: {e}")
        return []
    
    def run_sql_execute(self, sql: str, dry_run: bool = False) -> dict[str, Any]:
        """Execute SQL using qadmcli sql execute command."""
        if self.demo_mode and self.mock_cli:
            print(f"[DEMO] SQL: {sql[:80]}...")
            return {"success": True, "stdout": f"[DEMO] Would execute: {sql[:80]}...", "stderr": "", "returncode": 0}
        
        cmd = ["qadmcli", "sql", "execute", "-q", sql]
        if dry_run:
            print(f"[DRY-RUN] Would execute: {sql}")
            return {"success": True, "stdout": sql, "stderr": "", "returncode": 0}
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}
    
    def generate_child_table_with_fk(
        self, 
        table: str, 
        insert_count: int,
        fk_mappings: dict[str, list],  # column_name -> list of valid FK values
        other_columns: dict[str, Any],  # column_name -> (type, generator_func or static value)
        dry_run: bool = False,
        id_column: Optional[str] = None
    ) -> dict[str, Any]:
        """Generate child table data with proper FK values using SQL INSERT.
        
        Args:
            table: Table name
            insert_count: Number of rows to insert
            fk_mappings: Dict of FK column names to list of valid parent IDs
            other_columns: Dict of non-FK columns with their type and generator
            dry_run: If True, only print SQL without executing
            id_column: Optional PK column name (auto-detected if not provided)
        
        Returns:
            Dict with success status and generated IDs
        """
        generated_ids = []
        
        # Auto-detect ID column if not provided
        if not id_column:
            for col in other_columns:
                if col.endswith("_ID") and col not in fk_mappings:
                    id_column = col
                    break
        
        # Get starting ID
        start_id = 1
        if id_column:
            existing = self.get_existing_ids(table, id_column)
            if existing:
                start_id = max(existing) + 1
            elif self.demo_mode:
                # In demo mode, use predefined starting IDs
                demo_starts = {
                    "SUBSCRIPTION_ID": 1000,
                    "PAYMENT_ID": 5000,
                    "CLAIM_ID": 2000,
                    "DOCUMENT_ID": 10000
                }
                start_id = demo_starts.get(id_column, 1)
        
        sql_statements = []
        
        for i in range(insert_count):
            row_id = start_id + i
            
            # Build column list and values
            columns = []
            values = []
            
            # Add ID column if found
            if id_column:
                columns.append(id_column)
                values.append(str(row_id))
                generated_ids.append(row_id)
            
            # Add FK columns with random values from parent lists
            for fk_col, parent_ids in fk_mappings.items():
                if parent_ids:
                    fk_value = random.choice(parent_ids)
                    columns.append(fk_col)
                    values.append(str(fk_value))
            
            # Add other columns
            for col, col_config in other_columns.items():
                if col == id_column:
                    continue
                    
                col_type, generator = col_config if isinstance(col_config, tuple) else (col_config, None)
                columns.append(col)
                
                # Generate value based on type
                if col_type == "string":
                    val = generator() if callable(generator) else (generator or f"{col}_{row_id}")
                    values.append(f"'{val}'")
                elif col_type == "int":
                    val = generator() if callable(generator) else (generator or row_id)
                    values.append(str(val))
                elif col_type == "decimal":
                    val = generator() if callable(generator) else (generator or "100.00")
                    values.append(str(val))
                elif col_type == "date":
                    val = generator() if callable(generator) else datetime.now().strftime('%Y-%m-%d')
                    values.append(f"'{val}'")
                elif col_type == "timestamp":
                    val = generator() if callable(generator) else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    values.append(f"'{val}'")
                else:
                    values.append("NULL")
            
            # Build INSERT SQL
            cols_str = ", ".join(columns)
            vals_str = ", ".join(values)
            sql = f"INSERT INTO {self.library}.{table} ({cols_str}) VALUES ({vals_str})"
            sql_statements.append(sql)
            
            # Execute or collect
            if not dry_run:
                result = self.run_sql_execute(sql, dry_run=False)
                if not result["success"]:
                    error_str = result.get("stderr", "").upper()
                    if any(kw in error_str for kw in ['FOREIGN KEY', 'CONSTRAINT', 'PARENT KEY']):
                        print(f"  ⚠ FK violation for row {row_id}: {result['stderr'][:100]}")
                    else:
                        print(f"  ✗ Error inserting row {row_id}: {result['stderr'][:100]}")
                        return {
                            "success": False,
                            "table": table,
                            "errors": [result["stderr"]],
                            "generated_ids": generated_ids
                        }
        
        if dry_run:
            print(f"[DRY-RUN] Would execute {len(sql_statements)} INSERTs for {table}")
            for sql in sql_statements[:3]:
                print(f"  {sql}")
            if len(sql_statements) > 3:
                print(f"  ... and {len(sql_statements) - 3} more")
        else:
            print(f"  ✓ Inserted {len(generated_ids)} rows into {table}")
        
        return {
            "success": True,
            "table": table,
            "generated_ids": generated_ids,
            "sql_statements": sql_statements if dry_run else []
        }
    
    def process_table(self, table_name: str, dry_run: bool = False) -> dict[str, Any]:
        """Process a single table using its registry definition.
        
        Automatically chooses strategy:
        - "mockup": Uses qadmcli mockup generate (for tables without FKs)
        - "sql_fk": Uses FK-aware SQL generation (for tables with FKs)
        """
        table_def = self.registry.get(table_name)
        if not table_def:
            return {"success": False, "errors": [f"Table {table_name} not found in registry"]}
        
        print(f"\n=== Processing {table_name} (strategy: {table_def.strategy}) ===")
        
        if table_def.strategy == "reference":
            # Reference-only table - just query existing IDs
            pk_col = next((c.name for c in table_def.columns if c.is_pk), None)
            if pk_col:
                existing_ids = self.get_existing_ids(table_name, pk_col)
                self.generated_ids[table_name] = existing_ids
                print(f"✓ Found {len(existing_ids)} existing rows (reference-only)")
            return {"success": True, "table": table_name, "generated_ids": self.generated_ids.get(table_name, [])}
        
        if table_def.strategy == "mockup":
            # Use qadmcli mockup for tables without FK constraints
            config = {
                "insert": table_def.row_count,
                "update": 0,
                "delete": 0,
                "total": table_def.row_count,
                "dry_run": dry_run
            }
            result = self.run_mockup(table_name, config)
            if result["success"]:
                # Get generated IDs
                pk_col = next((c.name for c in table_def.columns if c.is_pk), None)
                if pk_col:
                    if self.demo_mode and "generated_ids" in result:
                        self.generated_ids[table_name] = result["generated_ids"]
                    else:
                        self.generated_ids[table_name] = self.get_existing_ids(table_name, pk_col)
                    print(f"✓ Generated {len(self.generated_ids[table_name])} rows")
            return result
        
        elif table_def.strategy == "sql_fk":
            # Use FK-aware SQL generation
            # Build FK mappings from parent tables
            fk_mappings = {}
            for col in table_def.columns:
                if col.fk_ref:
                    parent_table = col.fk_ref["table"]
                    parent_col = col.fk_ref["column"]
                    
                    # Get parent IDs from generated data or query
                    if parent_table in self.generated_ids:
                        parent_ids = self.generated_ids[parent_table]
                    else:
                        parent_ids = self.get_existing_ids(parent_table, parent_col)
                    
                    if not parent_ids:
                        return {
                            "success": False,
                            "errors": [f"No parent IDs available for {parent_table}.{parent_col}"]
                        }
                    
                    fk_mappings[col.name] = parent_ids
                    print(f"  ✓ FK {col.name} -> {parent_table}.{parent_col} ({len(parent_ids)} values)")
            
            # Build other_columns config
            other_columns = {}
            id_column = None
            for col in table_def.columns:
                if col.is_pk:
                    id_column = col.name
                elif not col.fk_ref and not col.is_identity:
                    generator = col.generator
                    # Convert string generators to lambdas if needed
                    if isinstance(generator, str):
                        static_val = generator
                        generator = lambda sv=static_val: sv
                    other_columns[col.name] = (col.col_type, generator)
            
            result = self.generate_child_table_with_fk(
                table=table_name,
                insert_count=table_def.row_count,
                fk_mappings=fk_mappings,
                other_columns=other_columns,
                dry_run=dry_run,
                id_column=id_column
            )
            
            if result["success"]:
                self.generated_ids[table_name] = result["generated_ids"]
                print(f"✓ Generated {len(result['generated_ids'])} rows with valid FKs")
            
            return result
        
        else:
            return {"success": False, "errors": [f"Unknown strategy: {table_def.strategy}"]}
    
    def run_mockup(self, table: str, config: dict[str, Any]) -> dict[str, Any]:
        """Run mockup command and return results."""
        if self.demo_mode and self.mock_cli:
            # Use mock CLI in demo mode
            print(f"[DEMO] Simulating: qadmcli mockup generate -n {table} -l {self.library} "
                  f"--insert {config.get('insert', 10)} --dry-run={config.get('dry_run', False)}")
            result = self.mock_cli.mockup_generate(
                table, self.library,
                config.get("insert", 10),
                config.get("update", 0),
                config.get("delete", 0),
                config.get("total", 10),
                config.get("dry_run", False)
            )
            print(result["stdout"])
            return {
                "success": True,
                "table": table,
                "stdout": result["stdout"],
                "stderr": "",
                "returncode": 0,
                "generated_ids": result.get("generated_ids", [])
            }
        
        cmd = [
            "qadmcli", "mockup", "generate",
            "-n", table,
            "-l", self.library,
            "--insert", str(config.get("insert", 10)),
            "--update", str(config.get("update", 0)),
            "--delete", str(config.get("delete", 0)),
            "--total", str(config.get("total", 10))
        ]
        
        if config.get("dry_run"):
            cmd.append("--dry-run")
        
        print(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False  # Don't raise on non-zero exit
            )
            
            # Check for FK constraint errors
            stderr = result.stderr.lower()
            stdout = result.stdout.lower()
            
            fk_errors = []
            if "constraint" in stderr or "constraint" in stdout:
                if "foreign" in stderr or "foreign" in stdout:
                    fk_errors.append("Foreign key constraint violation")
                if "parent" in stderr or "parent" in stdout:
                    fk_errors.append("Parent key not found")
                    
            if fk_errors:
                return {
                    "success": False,
                    "table": table,
                    "errors": fk_errors,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "table": table,
                    "errors": [f"Command failed with code {result.returncode}"],
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            
            return {
                "success": True,
                "table": table,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
            
        except Exception as e:
            return {
                "success": False,
                "table": table,
                "errors": [str(e)],
                "stdout": "",
                "stderr": str(e),
                "returncode": -1
            }
    
    def generate_insurance_data(self, config: Optional[dict] = None) -> dict[str, Any]:
        """Generate mockup data for insurance tables in proper order."""
        config = config or {}
        
        results = {
            "success": [],
            "failed": [],
            "errors": []
        }
        
        # Step 1: Generate INSURANCE_PRODUCTS (no FK dependencies)
        print("\n=== Step 1: Generating INSURANCE_PRODUCTS (no dependencies) ===")
        product_config = {
            "insert": config.get("products", 10),
            "update": 0,
            "delete": 0,
            "total": config.get("products", 10),
            "dry_run": config.get("dry_run", False)
        }
        
        result = self.run_mockup("INSURANCE_PRODUCTS", product_config)
        if result["success"]:
            results["success"].append("INSURANCE_PRODUCTS")
            # Get the generated product IDs
            if self.demo_mode and "generated_ids" in result:
                # In demo mode, use the IDs returned from mock
                self.generated_ids["INSURANCE_PRODUCTS"] = result["generated_ids"]
            else:
                self.generated_ids["INSURANCE_PRODUCTS"] = self.get_existing_ids("INSURANCE_PRODUCTS", "PRODUCT_ID")
            print(f"✓ Generated {len(self.generated_ids['INSURANCE_PRODUCTS'])} products")
        else:
            results["failed"].append("INSURANCE_PRODUCTS")
            results["errors"].append({"table": "INSURANCE_PRODUCTS", "errors": result["errors"]})
            print(f"✗ Failed: {result['errors']}")
        
        # Step 2: Generate SUBSCRIPTIONS (depends on CUSTOMERS and PRODUCTS)
        print("\n=== Step 2: Generating SUBSCRIPTIONS ===")
        print("Note: SUBSCRIPTIONS requires existing CUSTOMERS and PRODUCTS")
        
        # Get existing customer IDs
        customer_ids = self.get_existing_ids("CUSTOMERS", "CUST_ID")
        print(f"Found {len(customer_ids)} existing customers")
        
        product_ids = self.generated_ids.get("INSURANCE_PRODUCTS", [])
        if not product_ids:
            print("✗ Skipping SUBSCRIPTIONS: No products available")
            results["failed"].append("SUBSCRIPTIONS")
            results["errors"].append({"table": "SUBSCRIPTIONS", "errors": ["No parent products available"]})
        elif not customer_ids:
            print("✗ Skipping SUBSCRIPTIONS: No customers available")
            results["failed"].append("SUBSCRIPTIONS")
            results["errors"].append({"table": "SUBSCRIPTIONS", "errors": ["No parent customers available"]})
        else:
            # Use FK-aware SQL generation for SUBSCRIPTIONS
            print(f"✓ Found {len(customer_ids)} customers and {len(product_ids)} products")
            print(f"→ Generating SUBSCRIPTIONS with valid FK references...")
            
            # Define column configuration for SUBSCRIPTIONS
            other_columns = {
                "SUBSCRIPTION_ID": ("int", None),  # Auto-generated
                "START_DATE": ("date", lambda: (datetime.now().replace(day=1)).strftime('%Y-%m-%d')),
                "END_DATE": ("date", lambda: (datetime.now().replace(day=28)).strftime('%Y-%m-%d')),
                "PREMIUM_AMOUNT": ("decimal", lambda: round(random.uniform(500, 5000), 2)),
                "STATUS": ("string", lambda: random.choice(['ACTIVE', 'PENDING', 'SUSPENDED'])),
                "CREATED_AT": ("timestamp", None),
                "UPDATED_AT": ("timestamp", None)
            }
            
            result = self.generate_child_table_with_fk(
                table="SUBSCRIPTIONS",
                insert_count=config.get("subscriptions", 20),
                fk_mappings={
                    "CUST_ID": customer_ids,
                    "PRODUCT_ID": product_ids
                },
                other_columns=other_columns,
                dry_run=config.get("dry_run", False)
            )
            
            if result["success"]:
                results["success"].append("SUBSCRIPTIONS")
                self.generated_ids["SUBSCRIPTIONS"] = result["generated_ids"]
                print(f"✓ Generated {len(result['generated_ids'])} subscriptions with valid FKs")
            else:
                print(f"✗ Failed: {result.get('errors', ['Unknown error'])}")
                results["failed"].append("SUBSCRIPTIONS")
                results["errors"].append({"table": "SUBSCRIPTIONS", "errors": result.get("errors", [])})
        
        # Step 3: Generate PAYMENTS (depends on SUBSCRIPTIONS)
        print("\n=== Step 3: Generating PAYMENTS ===")
        sub_ids = self.generated_ids.get("SUBSCRIPTIONS", [])
        if not sub_ids:
            print("✗ Skipping PAYMENTS: No subscriptions available")
            results["failed"].append("PAYMENTS")
        else:
            payment_config = {
                "insert": config.get("payments", 50),
                "update": 0,
                "delete": 0,
                "total": config.get("payments", 50),
                "dry_run": config.get("dry_run", False)
            }
            
            result = self.run_mockup("PAYMENTS", payment_config)
            if result["success"]:
                results["success"].append("PAYMENTS")
                if self.demo_mode and "generated_ids" in result:
                    self.generated_ids["PAYMENTS"] = result["generated_ids"]
                print(f"✓ Generated {len(result.get('generated_ids', []))} payments")
            else:
                if any("foreign" in e.lower() or "parent" in e.lower() for e in result["errors"]):
                    print(f"✗ FK Constraint Error: {result['errors']}")
                else:
                    print(f"✗ Failed: {result['errors']}")
                results["failed"].append("PAYMENTS")
                results["errors"].append({"table": "PAYMENTS", "errors": result["errors"]})
        
        # Step 4: Generate CLAIMS (depends on SUBSCRIPTIONS)
        print("\n=== Step 4: Generating CLAIMS ===")
        if not sub_ids:
            print("✗ Skipping CLAIMS: No subscriptions available")
            results["failed"].append("CLAIMS")
        else:
            claims_config = {
                "insert": config.get("claims", 15),
                "update": 0,
                "delete": 0,
                "total": config.get("claims", 15),
                "dry_run": config.get("dry_run", False)
            }
            
            result = self.run_mockup("CLAIMS", claims_config)
            if result["success"]:
                results["success"].append("CLAIMS")
                if self.demo_mode and "generated_ids" in result:
                    self.generated_ids["CLAIMS"] = result["generated_ids"]
                else:
                    self.generated_ids["CLAIMS"] = self.get_existing_ids("CLAIMS", "CLAIM_ID")
                print(f"✓ Generated {len(self.generated_ids.get('CLAIMS', []))} claims")
            else:
                if any("foreign" in e.lower() or "parent" in e.lower() for e in result["errors"]):
                    print(f"✗ FK Constraint Error: {result['errors']}")
                else:
                    print(f"✗ Failed: {result['errors']}")
                results["failed"].append("CLAIMS")
                results["errors"].append({"table": "CLAIMS", "errors": result["errors"]})
        
        # Step 5: Generate CLAIM_DOCUMENTS (depends on CLAIMS)
        print("\n=== Step 5: Generating CLAIM_DOCUMENTS ===")
        claim_ids = self.generated_ids.get("CLAIMS", [])
        if not claim_ids:
            print("✗ Skipping CLAIM_DOCUMENTS: No claims available")
            results["failed"].append("CLAIM_DOCUMENTS")
        else:
            doc_config = {
                "insert": config.get("documents", 30),
                "update": 0,
                "delete": 0,
                "total": config.get("documents", 30),
                "dry_run": config.get("dry_run", False)
            }
            
            result = self.run_mockup("CLAIM_DOCUMENTS", doc_config)
            if result["success"]:
                results["success"].append("CLAIM_DOCUMENTS")
                if self.demo_mode and "generated_ids" in result:
                    self.generated_ids["CLAIM_DOCUMENTS"] = result["generated_ids"]
                print(f"✓ Generated {len(result.get('generated_ids', []))} claim documents")
            else:
                if any("foreign" in e.lower() or "parent" in e.lower() for e in result["errors"]):
                    print(f"✗ FK Constraint Error: {result['errors']}")
                else:
                    print(f"✗ Failed: {result['errors']}")
                results["failed"].append("CLAIM_DOCUMENTS")
                results["errors"].append({"table": "CLAIM_DOCUMENTS", "errors": result["errors"]})
        
        return results
    
    def generate_from_registry(self, dry_run: bool = False, 
                               table_filter: Optional[list[str]] = None) -> dict[str, Any]:
        """Generate data for all tables in registry order.
        
        Args:
            dry_run: If True, only show what would be done
            table_filter: Optional list of specific tables to process
        
        Returns:
            Dict with success/failed status for each table
        """
        results = {
            "success": [],
            "failed": [],
            "errors": []
        }
        
        # Get processing order
        if table_filter:
            # Process only specified tables in dependency order
            all_tables = self.registry.get_processing_order()
            tables_to_process = [t for t in all_tables if t in [tf.upper() for tf in table_filter]]
        else:
            tables_to_process = self.registry.get_processing_order()
        
        print(f"\nProcessing order: {' -> '.join(tables_to_process)}")
        
        for table_name in tables_to_process:
            result = self.process_table(table_name, dry_run=dry_run)
            
            if result["success"]:
                results["success"].append(table_name)
            else:
                results["failed"].append(table_name)
                results["errors"].append({
                    "table": table_name,
                    "errors": result.get("errors", ["Unknown error"])
                })
                # Continue with other tables even if one fails
        
        return results


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate mockup data with FK support using schema registry"
    )
    parser.add_argument("-l", "--library", default="GSLIBTST", help="Library name")
    parser.add_argument("--schema", "-s", help="YAML schema definition file")
    parser.add_argument("--tables", "-t", nargs="+", help="Specific tables to process")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    parser.add_argument("--demo", action="store_true", help="Demo mode (simulates without database)")
    parser.add_argument("--show-schema", action="store_true", help="Show default schema and exit")
    
    # Legacy options for insurance tables (backward compatibility)
    parser.add_argument("--products", type=int, default=10, help="[Legacy] Number of products")
    parser.add_argument("--subscriptions", type=int, default=20, help="[Legacy] Number of subscriptions")
    parser.add_argument("--payments", type=int, default=50, help="[Legacy] Number of payments")
    parser.add_argument("--claims", type=int, default=15, help="[Legacy] Number of claims")
    parser.add_argument("--documents", type=int, default=30, help="[Legacy] Number of claim documents")
    parser.add_argument("--legacy", action="store_true", help="Use legacy insurance table mode")
    
    args = parser.parse_args()
    
    # Show default schema if requested
    if args.show_schema:
        registry = SchemaRegistry.create_insurance_schema(args.library)
        print("# Default Insurance Schema")
        print("# Save this to a YAML file and customize as needed:\n")
        for name in registry.tables:
            table = registry.get(name)
            if not table:
                continue
            print(f"# Table: {name}")
            print(f"#   Strategy: {table.strategy}")
            print(f"#   Rows: {table.row_count}")
            print(f"#   Depends on: {table.depends_on}")
            print("#   Columns:")
            for col in table.columns:
                fk_info = f" -> {col.fk_ref['table']}.{col.fk_ref['column']}" if col.fk_ref else ""
                pk_info = " [PK]" if col.is_pk else ""
                identity_info = " [IDENTITY]" if col.is_identity else ""
                print(f"#     - {col.name}: {col.col_type}{pk_info}{identity_info}{fk_info}")
            print()
        return 0
    
    print("=" * 60)
    print("Mockup Data Generator with FK Support")
    if args.demo:
        print("[DEMO MODE - No database connection required]")
    print("=" * 60)
    
    # Load schema from YAML or use default
    default_schema = os.path.join(os.path.dirname(__file__), "..", "schemas", "insurance.yaml")
    
    if args.schema:
        print(f"Loading schema from: {args.schema}")
        registry = SchemaRegistry.from_yaml(args.schema)
    elif os.path.exists(default_schema):
        print(f"Using default schema: {default_schema}")
        registry = SchemaRegistry.from_yaml(default_schema)
    else:
        print("Using built-in insurance schema")
        registry = SchemaRegistry.create_insurance_schema(args.library)
    
    manager = MockupFKManager(library=args.library, demo_mode=args.demo, registry=registry)
    
    # Use legacy mode or new registry-based mode
    if args.legacy:
        # Legacy insurance table mode
        print("\n[Using legacy mode]")
        config = {
            "products": args.products,
            "subscriptions": args.subscriptions,
            "payments": args.payments,
            "claims": args.claims,
            "documents": args.documents,
            "dry_run": args.dry_run
        }
        results = manager.generate_insurance_data(config)
    else:
        # New registry-based mode
        results = manager.generate_from_registry(
            dry_run=args.dry_run,
            table_filter=args.tables
        )
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"✓ Successful: {', '.join(results['success']) if results['success'] else 'None'}")
    print(f"✗ Failed: {', '.join(results['failed']) if results['failed'] else 'None'}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  - {error['table']}: {error['errors']}")
    
    return 0 if not results['failed'] else 1


if __name__ == "__main__":
    sys.exit(main())
