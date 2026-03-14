"""Connection configuration models."""

import os
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AS400Connection(BaseModel):
    """AS400 connection settings."""

    host: str = Field(..., description="AS400 hostname or IP address")
    user: str = Field(..., description="AS400 username")
    password: str = Field(..., description="AS400 password")
    port: int = Field(default=8471, description="DRDA port (default: 8471)")
    ssl: bool = Field(default=True, description="Use SSL connection")
    database: str = Field(default="*LOCAL", description="Database name")
    
    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Host cannot be empty")
        return v.strip()

    @field_validator("user", "password")
    @classmethod
    def validate_credentials(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Credentials cannot be empty")
        return v.strip()


class DefaultsConfig(BaseModel):
    """Default settings."""

    library: str = Field(default="QGPL", description="Default library/schema")
    journal_library: str = Field(default="QSYS2", description="Default journal library")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )


class ConnectionConfig(BaseModel):
    """Root connection configuration."""

    as400: AS400Connection
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @classmethod
    def from_yaml(cls, config_path: str) -> "ConnectionConfig":
        """Load configuration from YAML file with environment variable substitution."""
        import yaml
        
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Substitute environment variables: ${VAR} or ${VAR:-default}
        def env_substitute(match: Any) -> str:
            var_expr = match.group(1)
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                return os.environ.get(var_name, default)
            return os.environ.get(var_expr, "")
        
        content = re.sub(r"\$\{([^}]+)\}", env_substitute, content)
        data = yaml.safe_load(content)
        
        return cls(**data)
    
    def get_jdbc_url(self) -> str:
        """Generate JDBC URL for jt400."""
        ssl_param = ";ssl=true" if self.as400.ssl else ""
        return (
            f"jdbc:as400://{self.as400.host}:{self.as400.port}"
            f"/{self.as400.database}{ssl_param}"
        )
    
    def get_connection_properties(self) -> dict[str, str]:
        """Get connection properties for jt400."""
        props = {
            "user": self.as400.user,
            "password": self.as400.password,
        }
        if self.as400.ssl:
            props["ssl"] = "true"
        return props
