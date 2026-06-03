"""AS400 Connection Pool - Manages persistent JT400 connections."""

import jpype
import jpype.imports
import logging
import time
from typing import Optional, List
from dataclasses import dataclass, field
from queue import Queue, Empty
import threading

logger = logging.getLogger(__name__)


class IntegerCursor(int):
    """An integer subclass that behaves like a cursor for non-SELECT statements."""
    def close(self):
        pass
        
    def fetchall(self):
        return []
        
    def fetchone(self):
        return None


class JDBCResultCursor:
    """Cursor-like wrapper for Java PreparedStatement and ResultSet."""
    def __init__(self, prep_stmt, result_set):
        self._prep_stmt = prep_stmt
        self._rs = result_set
        self._meta = result_set.getMetaData()
        self._col_count = self._meta.getColumnCount()
        self._closed = False
        
    def get_column_names(self) -> list:
        """Get column names from result set metadata."""
        columns = []
        for i in range(1, self._col_count + 1):
            try:
                name = self._meta.getColumnLabel(i)
                if not name:
                    name = self._meta.getColumnName(i)
            except:
                name = f"col{i}"
            # Convert Java String to Python str
            columns.append(str(name))
        return columns
    
    def get_column_types(self) -> list:
        """Get JDBC column type codes."""
        types = []
        for i in range(1, self._col_count + 1):
            try:
                types.append(self._meta.getColumnType(i))
            except:
                types.append(None)
        return types
        
    def fetchall(self) -> List[tuple]:
        """Fetch all rows from result set."""
        rows = []
        try:
            while self._rs.next():
                row = []
                for i in range(1, self._col_count + 1):
                    row.append(self._rs.getObject(i))
                rows.append(tuple(row))
            return rows
        except Exception as e:
            logger.error(f"Error fetching all rows: {e}")
            raise

    def fetchall_dicts(self) -> List[dict]:
        """Fetch all rows as dicts with column names. Converts Java types to Python."""
        import datetime
        from decimal import Decimal
        
        columns = self.get_column_names()
        rows = self.fetchall()
        result = []
        for row in rows:
            d = {}
            for i, col in enumerate(columns):
                val = row[i] if i < len(row) else None
                # Convert Java objects to Python-native types for JSON serialization
                if val is not None:
                    java_class = str(type(val))
                    if 'java.sql.Timestamp' in java_class or 'java.util.Date' in java_class:
                        val = str(val)
                    elif 'java.math.BigDecimal' in java_class:
                        val = float(str(val))
                    elif 'java.lang.Integer' in java_class or 'java.lang.Long' in java_class:
                        val = int(val)
                    elif 'java.lang.Float' in java_class or 'java.lang.Double' in java_class:
                        val = float(val)
                    elif 'java.lang.Boolean' in java_class:
                        val = bool(val)
                    elif 'byte' in java_class or 'Byte' in java_class:
                        try:
                            val = bytes(val).hex()
                        except:
                            val = str(val)
                    else:
                        val = str(val)
                d[col] = val
            result.append(d)
        return result
        
    def fetchone(self) -> Optional[tuple]:
        try:
            if self._rs.next():
                row = []
                for i in range(1, self._col_count + 1):
                    row.append(self._rs.getObject(i))
                return tuple(row)
            return None
        except Exception as e:
            logger.error(f"Error fetching single row: {e}")
            raise
        
    def close(self):
        if not self._closed:
            try:
                self._rs.close()
            except:
                pass
            try:
                self._prep_stmt.close()
            except:
                pass
            self._closed = True


@dataclass
class ConnectionConfig:
    """AS400 connection configuration."""
    host: str
    user: str
    password: str
    library: str = ""
    port: int = 446
    naming: str = "system"  # system or sql
    transactions: str = "readcommitted"


@dataclass
class PoolStats:
    """Connection pool statistics."""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_queries: int = 0
    total_errors: int = 0
    avg_query_time_ms: float = 0.0
    uptime_seconds: float = 0.0


class AS400Connection:
    """Wrapper around JT400 connection."""
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._conn = None
        self._last_used = time.time()
        self._in_use = False
        self._create_connection()
    def _create_connection(self):
        """Create JT400 JDBC connection."""
        logger.error("DEBUG LOG: Executing _create_connection in NEW connection_pool.py")
        from java.sql import DriverManager
        from java.util import Properties
        import os
        
        try:
            port = os.getenv("AS400_PORT", "8471")
            ssl_val = os.getenv("AS400_SSL", "false").lower() == "true"
            ssl_param = ";ssl=true" if ssl_val else ";ssl=false"
            
            # In JT400 JDBC, the path in `jdbc:as400://host:port/path` represents the default schema/library list.
            # Do NOT use *LOCAL or *LIBL as a schema path, as they are invalid schema names and cause PWS0082.
            schema_path = ""
            if self.config.library and self.config.library != "*LIBL" and self.config.library != "*LOCAL":
                schema_path = f"/{self.config.library}"
            
            jdbc_url = f"jdbc:as400://{self.config.host}:{port}{schema_path}{ssl_param}"
            
            props = Properties()
            props.put("user", self.config.user)
            props.put("password", self.config.password)
            props.put("translate binary", "true")
            props.put("use block insert", "true")
            props.put("use block update", "true")
            props.put("block size", "512")
            if self.config.library and self.config.library != "*LIBL":
                props.put("libraries", self.config.library)
            
            logger.info(f"Connecting to AS400 via JDBC URL: {jdbc_url}")
            
            # Create JDBC connection using DriverManager
            self._conn = DriverManager.getConnection(jdbc_url, props)
            
            # Library list is already set via JDBC URL path and props["libraries"]
            
            logger.info(f"✅ Connected to AS400: {self.config.host}")
            
        except Exception as e:
            # High priority log to print values
            logger.error(f"DIAGNOSTIC LOG - library: {self.config.library!r}, jdbc_url: {jdbc_url!r}, user: {self.config.user!r}")
            # Try to log properties safely (convert java Properties to string or dict)
            try:
                logger.error(f"DIAGNOSTIC LOG - props: {str(props)}")
            except Exception:
                pass
            logger.error(f"Failed to connect to AS400: {e}")
            raise
    
    def execute(self, sql: str, params: tuple | None = None):
        """Execute single SQL statement."""
        try:
            prep_stmt = self._conn.prepareStatement(sql.rstrip(';'))
            
            if params:
                for idx, value in enumerate(params, 1):
                    self._set_parameter(prep_stmt, idx, value)
            
            # Execute statement natively using JDBC execute()
            has_result_set = prep_stmt.execute()
            
            if has_result_set:
                rs = prep_stmt.getResultSet()
                self._last_used = time.time()
                return JDBCResultCursor(prep_stmt, rs)
            else:
                result = prep_stmt.getUpdateCount()
                prep_stmt.close()
                self._last_used = time.time()
                return IntegerCursor(result)
        except Exception as e:
            logger.error(f"SQL execution failed: {sql[:200]}... Error: {e}")
            raise
    
    def execute_batch(self, sql: str, params_list: List[dict]) -> int:
        """Execute batch SQL with parameters."""
        orig_autocommit = True
        try:
            # Temporarily disable auto-commit to maximize throughput
            orig_autocommit = self._conn.getAutoCommit()
            if orig_autocommit:
                self._conn.setAutoCommit(False)
                
            prep_stmt = self._conn.prepareStatement(sql)
            
            for params in params_list:
                # Set parameters
                for key, value in params.items():
                    self._set_parameter(prep_stmt, int(key), value)
                prep_stmt.addBatch()
            
            # Execute batch
            results = prep_stmt.executeBatch()
            self._conn.commit()
            prep_stmt.close()
            
            if orig_autocommit:
                self._conn.setAutoCommit(True)
                
            self._last_used = time.time()
            return sum(results)
            
        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            try:
                self._conn.rollback()
            except:
                pass
            try:
                if orig_autocommit:
                    self._conn.setAutoCommit(True)
            except:
                pass
            raise
    
    def _set_parameter(self, prep_stmt, idx: int, value):
        """Set parameter in prepared statement."""
        from java.sql import Types
        import jpype
        import datetime
        from decimal import Decimal
        
        if value is None:
            prep_stmt.setNull(idx, Types.VARCHAR)
        elif isinstance(value, bool):
            prep_stmt.setBoolean(idx, value)
        elif isinstance(value, int):
            prep_stmt.setInt(idx, value)
        elif isinstance(value, float):
            prep_stmt.setDouble(idx, value)
        elif isinstance(value, Decimal):
            from java.math import BigDecimal
            prep_stmt.setBigDecimal(idx, BigDecimal(str(value)))
        elif isinstance(value, datetime.datetime):
            import java.sql
            millis = int(value.timestamp() * 1000)
            prep_stmt.setTimestamp(idx, java.sql.Timestamp(millis))
        elif isinstance(value, datetime.date):
            import java.sql
            date_str = value.strftime("%Y-%m-%d")
            prep_stmt.setDate(idx, java.sql.Date.valueOf(date_str))
        elif isinstance(value, datetime.time):
            import java.sql
            time_str = value.strftime("%H:%M:%S")
            prep_stmt.setTime(idx, java.sql.Time.valueOf(time_str))
        elif isinstance(value, (bytes, bytearray)):
            java_bytes = jpype.JArray(jpype.JByte)(value)
            prep_stmt.setBytes(idx, java_bytes)
        elif isinstance(value, dict) and value.get("__type__") == "bytes":
            hex_val = value.get("value", "")
            try:
                byte_val = bytes.fromhex(hex_val)
                java_bytes = jpype.JArray(jpype.JByte)(byte_val)
                prep_stmt.setBytes(idx, java_bytes)
            except ValueError:
                prep_stmt.setString(idx, hex_val)
        else:
            prep_stmt.setString(idx, str(value))
    
    def is_valid(self) -> bool:
        """Check if connection is still valid."""
        try:
            if self._conn is None:
                return False
            
            # Test with simple query
            cursor = self._conn.prepareStatement("SELECT 1 FROM SYSIBM.SYSDUMMY1")
            cursor.executeQuery()
            cursor.close()
            return True
        except:
            return False
    
    def close(self):
        """Close connection."""
        if self._conn:
            try:
                self._conn.close()
            except:
                pass
                
    def commit(self):
        """Commit transaction."""
        if self._conn:
            try:
                self._conn.commit()
            except Exception as e:
                logger.error(f"Commit failed: {e}")
                raise

    def rollback(self):
        """Rollback transaction."""
        if self._conn:
            try:
                self._conn.rollback()
            except Exception as e:
                logger.error(f"Rollback failed: {e}")
                raise


class ConnectionPool:
    """Thread-safe connection pool for AS400."""
    
    def __init__(self, config: ConnectionConfig, pool_size: int = 5):
        self.config = config
        self.pool_size = pool_size
        self._pool: Queue = Queue()
        self._all_connections: List[AS400Connection] = []
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._stats = PoolStats()
        
        # Initialize pool
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Create initial connections."""
        logger.info(f"Initializing connection pool with {self.pool_size} connections...")
        
        for i in range(self.pool_size):
            try:
                conn = AS400Connection(self.config)
                self._pool.put(conn)
                self._all_connections.append(conn)
                logger.debug(f"Connection {i+1}/{self.pool_size} created")
            except Exception as e:
                logger.error(f"Failed to create connection {i+1}: {e}")
        
        self._stats.total_connections = len(self._all_connections)
        logger.info(f"✅ Connection pool initialized: {self._stats.total_connections} connections")
    
    def get_connection(self, timeout: float = 10.0) -> Optional[AS400Connection]:
        """Get a connection from the pool."""
        try:
            conn = self._pool.get(timeout=timeout)
            
            # Check if connection is still valid
            if not conn.is_valid():
                logger.warning("Connection invalid, recreating...")
                conn.close()
                conn = AS400Connection(self.config)
                self._all_connections.remove(conn)
                self._all_connections.append(conn)
            
            conn._in_use = True
            self._stats.active_connections += 1
            self._stats.idle_connections = self._pool.qsize()
            
            return conn
            
        except Empty:
            logger.error(f"Timeout waiting for connection ({timeout}s)")
            return None
    
    def release_connection(self, conn: AS400Connection):
        """Release connection back to pool."""
        conn._in_use = False
        conn._last_used = time.time()
        self._stats.active_connections -= 1
        self._stats.idle_connections = self._pool.qsize() + 1
        self._pool.put(conn)
    
    def execute_batch(self, sql: str, params_list: List[dict]) -> int:
        """Execute batch using connection from pool."""
        conn = self.get_connection()
        if not conn:
            raise Exception("No available connections")
        
        try:
            start_time = time.time()
            result = conn.execute_batch(sql, params_list)
            
            # Update stats
            elapsed = (time.time() - start_time) * 1000
            self._stats.total_queries += 1
            self._stats.avg_query_time_ms = (
                (self._stats.avg_query_time_ms * (self._stats.total_queries - 1) + elapsed) 
                / self._stats.total_queries
            )
            
            return result
        except Exception as e:
            self._stats.total_errors += 1
            raise
        finally:
            self.release_connection(conn)
    
    def execute_query(self, sql: str, params: list | None = None) -> dict:
        """Execute a SELECT query and return structured results.
        
        Args:
            sql: SQL statement
            params: Optional list of positional parameter values
        
        Returns:
            dict with columns (list), rows (list of lists), row_count
        """
        conn = self.get_connection()
        if not conn:
            raise Exception("No available connections")
        
        try:
            start_time = time.time()
            
            if params:
                cursor = conn.execute(sql, tuple(params))
            else:
                cursor = conn.execute(sql)
            
            # Check if this is a result cursor (SELECT) or int cursor (DML)
            if isinstance(cursor, JDBCResultCursor):
                columns = cursor.get_column_names()
                rows_raw = cursor.fetchall()
                # Convert tuples to lists for JSON serialization
                rows = []
                for row in rows_raw:
                    clean = []
                    for val in row:
                        if val is not None:
                            java_class = str(type(val))
                            if any(x in java_class for x in ['java.sql.Timestamp', 'java.util.Date']):
                                clean.append(str(val))
                            elif 'java.math.BigDecimal' in java_class:
                                clean.append(float(str(val)))
                            elif any(x in java_class for x in ['java.lang.Integer', 'java.lang.Long']):
                                clean.append(int(val))
                            elif any(x in java_class for x in ['java.lang.Float', 'java.lang.Double']):
                                clean.append(float(val))
                            elif 'java.lang.Boolean' in java_class:
                                clean.append(bool(val))
                            elif any(x in java_class for x in ['byte', 'Byte']):
                                try:
                                    clean.append(bytes(val).hex())
                                except:
                                    clean.append(str(val))
                            else:
                                clean.append(str(val))
                        else:
                            clean.append(None)
                    rows.append(clean)
                cursor.close()
            else:
                # DML statement - no result rows
                columns = []
                rows = []
                cursor.close()
            
            elapsed = (time.time() - start_time) * 1000
            
            # Update stats
            self._stats.total_queries += 1
            self._stats.avg_query_time_ms = (
                (self._stats.avg_query_time_ms * (self._stats.total_queries - 1) + elapsed)
                / self._stats.total_queries
            )
            
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "execution_time_ms": round(elapsed, 2)
            }
        except Exception as e:
            self._stats.total_errors += 1
            raise
        finally:
            self.release_connection(conn)
    
    def get_stats(self) -> PoolStats:
        """Get pool statistics."""
        self._stats.uptime_seconds = time.time() - self._start_time
        self._stats.idle_connections = self._pool.qsize()
        self._stats.active_connections = self._stats.total_connections - self._stats.idle_connections
        return self._stats
    
    def close_all(self):
        """Close all connections in pool."""
        logger.info("Closing all connections...")
        for conn in self._all_connections:
            try:
                conn.close()
            except:
                pass
        self._all_connections.clear()
        logger.info("✅ All connections closed")
