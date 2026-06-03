"""FastAPI REST Server - Exposes AS400 operations via HTTP API."""

import logging
import os
import time
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

from .jvm_manager import JVMManager
from .connection_pool import ConnectionPool, ConnectionConfig, PoolStats

# Import mockup components (now run in agent)
from .mockup import MockupManager, MockupConfig

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="QADMCLI AS400 Agent",
    description="High-performance AS400 operations via persistent JVM",
    version="0.1.0"
)

# Global state
jvm_manager: Optional[JVMManager] = None
connection_pool: Optional[ConnectionPool] = None


# Request/Response Models
class SQLRequest(BaseModel):
    sql: str
    library: Optional[str] = ""
    params: Optional[List] = None


class BatchSQLRequest(BaseModel):
    sql: str
    params: List[dict]
    library: Optional[str] = ""


class BatchResponse(BaseModel):
    status: str
    rows_affected: int
    execution_time_ms: float


class QueryResponse(BaseModel):
    status: str
    columns: List[str] = []
    rows: List[List] = []
    row_count: int = 0
    execution_time_ms: float = 0.0


class HealthResponse(BaseModel):
    status: str
    jvm_running: bool
    jt400_version: str
    pool_stats: Optional[dict] = None
    uptime_seconds: float
    timestamp: str


class StatusResponse(BaseModel):
    agent_version: str
    jvm_status: str
    jt400_status: str
    connection_pool: Optional[dict] = None
    uptime: str


# Mockup Generation Models
class MockupGenerateRequest(BaseModel):
    table: str
    library: str
    total_transactions: int = 1000
    batch_size: int = 100
    insert_ratio: int = 60
    update_ratio: int = 20
    delete_ratio: int = 20
    dry_run: bool = False
    random_pks: bool = False
    schema_hints: Optional[dict] = None


class MockupGenerateResponse(BaseModel):
    status: str
    table: str
    library: str
    inserted: int
    updated: int
    deleted: int
    total_transactions: int
    execution_time_ms: float
    message: str


# Startup/Shutdown Events
@app.on_event("startup")
async def startup_event():
    """Initialize JVM and connection pool on startup."""
    global jvm_manager, connection_pool
    
    logger.info("🚀 Starting AS400 Agent...")
    
    # Load config
    from pathlib import Path
    import json
    
    config_path = Path.home() / ".qadmcli" / "agent.json"
    if config_path.exists():
        with open(config_path) as f:
            agent_config = json.load(f)
    else:
        agent_config = {
            "jt400_path": "/opt/jt400/jt400.jar",
            "pool_size": 5,
            "as400": {
                "host": "161.82.146.249",
                "user": "",
                "password": "",
                "library": ""
            }
        }
    
    # Start JVM
    jvm_manager = JVMManager(jt400_path=agent_config.get("jt400_path", "/opt/jt400/jt400.jar"))
    jvm_manager.start_jvm()
    
    # Initialize connection pool with env var fallback for credentials
    as400_config = agent_config.get("as400", {})
    pool_config = ConnectionConfig(
        host=as400_config.get("host") or os.getenv("AS400_HOST", "161.82.146.249"),
        user=as400_config.get("user") or os.getenv("AS400_USER", ""),
        password=as400_config.get("password") or os.getenv("AS400_PASSWORD", ""),
        library=as400_config.get("library") or os.getenv("AS400_LIBRARY", "*LIBL")
    )
    
    pool_size = agent_config.get("pool_size", 5)
    connection_pool = ConnectionPool(pool_config, pool_size=pool_size)
    
    logger.info("✅ AS400 Agent ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global jvm_manager, connection_pool
    
    logger.info("🛑 Shutting down AS400 Agent...")
    
    if connection_pool:
        connection_pool.close_all()
    
    if jvm_manager:
        jvm_manager.shutdown_jvm()
    
    logger.info("✅ AS400 Agent stopped")


# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    if not jvm_manager or not jvm_manager.is_running():
        return HealthResponse(
            status="unhealthy",
            jvm_running=False,
            jt400_version="JVM not started",
            uptime_seconds=0,
            timestamp=datetime.now().isoformat()
        )
    
    pool_stats = None
    if connection_pool:
        stats = connection_pool.get_stats()
        pool_stats = {
            "total_connections": stats.total_connections,
            "active_connections": stats.active_connections,
            "idle_connections": stats.idle_connections,
            "total_queries": stats.total_queries,
            "avg_query_time_ms": round(stats.avg_query_time_ms, 2)
        }
    
    return HealthResponse(
        status="healthy",
        jvm_running=True,
        jt400_version=jvm_manager.get_jt400_version(),
        pool_stats=pool_stats,
        uptime_seconds=stats.uptime_seconds if connection_pool else 0,
        timestamp=datetime.now().isoformat()
    )


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get detailed agent status."""
    jvm_status = "running" if jvm_manager and jvm_manager.is_running() else "stopped"
    jt400_status = "loaded" if jvm_manager and jvm_manager.is_running() else "not loaded"
    
    pool_info = None
    if connection_pool:
        stats = connection_pool.get_stats()
        hours = int(stats.uptime_seconds // 3600)
        minutes = int((stats.uptime_seconds % 3600) // 60)
        pool_info = {
            "size": stats.total_connections,
            "active": stats.active_connections,
            "idle": stats.idle_connections,
            "total_queries": stats.total_queries,
            "total_errors": stats.total_errors,
            "avg_query_time_ms": round(stats.avg_query_time_ms, 2),
            "uptime": f"{hours}h {minutes}m"
        }
    
    return StatusResponse(
        agent_version="0.1.0",
        jvm_status=jvm_status,
        jt400_status=jt400_status,
        connection_pool=pool_info,
        uptime=f"{hours}h {minutes}m" if connection_pool else "0h 0m"
    )


@app.post("/sql/execute")
async def execute_sql(request: SQLRequest):
    """Execute a single SQL statement."""
    if not connection_pool:
        raise HTTPException(status_code=503, detail="Connection pool not initialized")
    
    try:
        conn = connection_pool.get_connection()
        if not conn:
            raise HTTPException(status_code=503, detail="No available connections")
        
        start_time = __import__('time').time()
        result = conn.execute(request.sql)
        elapsed_ms = (__import__('time').time() - start_time) * 1000
        
        connection_pool.release_connection(conn)
        
        return {
            "status": "success",
            "rows_affected": result,
            "execution_time_ms": round(elapsed_ms, 2)
        }
        
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sql/query", response_model=QueryResponse)
async def execute_query(request: SQLRequest):
    """Execute a SQL SELECT query and return structured results (columns + rows)."""
    if not connection_pool:
        raise HTTPException(status_code=503, detail="Connection pool not initialized")
    
    try:
        result = connection_pool.execute_query(request.sql, request.params)
        return QueryResponse(
            status="success",
            columns=result["columns"],
            rows=result["rows"],
            row_count=result["row_count"],
            execution_time_ms=result["execution_time_ms"]
        )
    except Exception as e:
        logger.error(f"SQL query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sql/batch", response_model=BatchResponse)
async def execute_batch(request: BatchSQLRequest):
    """Execute batch SQL with parameters (FAST!)."""
    if not connection_pool:
        raise HTTPException(status_code=503, detail="Connection pool not initialized")
    
    try:
        start_time = __import__('time').time()
        rows_affected = connection_pool.execute_batch(request.sql, request.params)
        elapsed_ms = (__import__('time').time() - start_time) * 1000
        
        return BatchResponse(
            status="success",
            rows_affected=rows_affected,
            execution_time_ms=round(elapsed_ms, 2)
        )
        
    except Exception as e:
        logger.error(f"Batch execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mockup/insert")
async def mockup_insert(request: BatchSQLRequest):
    """Execute mockup bulk insert."""
    return await execute_batch(request)


@app.post("/mockup/update")
async def mockup_update(request: BatchSQLRequest):
    """Execute mockup bulk update."""
    return await execute_batch(request)


@app.post("/mockup/delete")
async def mockup_delete(request: BatchSQLRequest):
    """Execute mockup bulk delete."""
    return await execute_batch(request)


@app.post("/mockup/generate", response_model=MockupGenerateResponse)
async def generate_mockup(request: MockupGenerateRequest):
    """Generate complete mockup data (ALL logic runs in agent!)."""
    if not connection_pool:
        raise HTTPException(status_code=503, detail="Connection pool not initialized")
    
    start_time = time.time()
    
    try:
        logger.info(f"🎯 Mockup generate request: {request.library}.{request.table} "
                   f"({request.total_transactions} transactions, batch_size={request.batch_size})")
        
        # Get connection from pool
        conn = connection_pool.get_connection()
        if not conn:
            raise HTTPException(status_code=503, detail="No available connections")
        
        try:
            # Create MockupManager with connection
            mockup_mgr = MockupManager(conn, schema_hints=request.schema_hints)
            
            # Create config
            config = MockupConfig(
                insert_ratio=request.insert_ratio,
                update_ratio=request.update_ratio,
                delete_ratio=request.delete_ratio,
                total_transactions=request.total_transactions,
                batch_size=request.batch_size,
                dry_run=request.dry_run,
                random_pks=request.random_pks
            )
            
            # Generate mock data (all logic runs in agent!)
            result = mockup_mgr.generate_mock_data(
                request.table,
                request.library,
                config
            )
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            stats = result.get('stats', {})
            inserted_count = stats.get('inserted', 0)
            updated_count = stats.get('updated', 0)
            deleted_count = stats.get('deleted', 0)
            
            logger.info(f"✅ Mockup generation complete: "
                       f"{inserted_count} inserts, {updated_count} updates, "
                       f"{deleted_count} deletes in {elapsed_ms:.0f}ms")
            
            return MockupGenerateResponse(
                status="success",
                table=request.table,
                library=request.library,
                inserted=inserted_count,
                updated=updated_count,
                deleted=deleted_count,
                total_transactions=request.total_transactions,
                execution_time_ms=round(elapsed_ms, 2),
                message=f"Generated {inserted_count + updated_count + deleted_count} "
                       f"transactions in {elapsed_ms/1000:.2f}s"
            )
            
        finally:
            # Return connection to pool
            connection_pool.release_connection(conn)
    
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ Mockup generation failed after {elapsed_ms:.0f}ms: {e}")
        raise HTTPException(status_code=500, detail=str(e))
