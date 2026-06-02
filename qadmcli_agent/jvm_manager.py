"""JVM Manager - Handles JVM lifecycle and JT400 initialization."""

import jpype
import jpype.imports
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class JVMManager:
    """Manages JVM lifecycle and JT400 library loading."""
    
    def __init__(self, jt400_path: str = "/opt/jt400/jt400.jar"):
        self.jt400_path = jt400_path
        self._jvm_started = False
        
    def start_jvm(self) -> bool:
        """Start JVM and load JT400."""
        if jpype.isJVMStarted():
            logger.info("JVM already running")
            self._jvm_started = True
            return True
        
        try:
            logger.info(f"Starting JVM with JT400: {self.jt400_path}")
            
            # Verify JT400 exists
            if not Path(self.jt400_path).exists():
                raise FileNotFoundError(f"JT400 not found: {self.jt400_path}")
            
            # Start JVM
            jpype.startJVM(
                classpath=[self.jt400_path],
                convertStrings=False
            )
            
            # Import JT400 classes to verify they're available
            from com.ibm.as400.access import AS400JDBCConnection
            
            self._jvm_started = True
            logger.info("✅ JVM started successfully with JT400")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start JVM: {e}")
            raise
    
    def shutdown_jvm(self):
        """Shutdown JVM (only when agent is stopping)."""
        if jpype.isJVMStarted():
            logger.info("Shutting down JVM...")
            jpype.shutdownJVM()
            self._jvm_started = False
            logger.info("✅ JVM shut down")
    
    def is_running(self) -> bool:
        """Check if JVM is running."""
        return jpype.isJVMStarted() and self._jvm_started
    
    def get_jt400_version(self) -> str:
        """Get JT400 version string."""
        if not self.is_running():
            return "JVM not started"
        
        try:
            from com.ibm.as400.access import AS400
            return f"JT400 loaded (JVM running)"
        except:
            return "JT400 not available"
