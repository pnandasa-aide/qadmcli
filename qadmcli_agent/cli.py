"""QADMCLI Agent CLI - Start/stop/status commands for AS400 agent daemon."""

import click
import subprocess
import time
import os
import sys
import signal
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

AGENT_HOST = "0.0.0.0"  # Listen on all interfaces to allow container access
AGENT_PORT = 8765
PID_FILE = Path.home() / ".qadmcli" / "agent.pid"
LOG_FILE = Path.home() / ".qadmcli" / "agent.log"


def is_agent_running() -> bool:
    """Check if agent is running."""
    if not PID_FILE.exists():
        return False
    
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        
        # Check if process exists
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        # Process not running, clean up PID file
        PID_FILE.unlink(missing_ok=True)
        return False
    except PermissionError:
        # Process exists but we don't own it
        return True


def get_agent_pid() -> int:
    """Get agent PID."""
    if not PID_FILE.exists():
        return -1
    
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except:
        return -1


@click.group()
def agent():
    """Manage AS400 Agent Daemon."""
    pass


@agent.command()
@click.option('--host', default=AGENT_HOST, help='Agent host address')
@click.option('--port', default=AGENT_PORT, help='Agent port')
@click.option('--jt400-path', default='/opt/jt400/jt400.jar', help='Path to jt400.jar')
@click.option('--pool-size', default=5, help='Connection pool size')
@click.option('--foreground', is_flag=True, help='Run in foreground (for containers)')
def start(host: str, port: int, jt400_path: str, pool_size: int, foreground: bool):
    """Start AS400 Agent Daemon."""
    if is_agent_running() and not foreground:
        pid = get_agent_pid()
        click.echo(f"⚠️  Agent already running (PID: {pid})")
        click.echo(f"   URL: http://{AGENT_HOST}:{AGENT_PORT}")
        return
    
    # Ensure config directory exists
    config_dir = Path.home() / ".qadmcli"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Create agent config
    import json
    config = {
        "jt400_path": jt400_path,
        "pool_size": pool_size,
        "host": host,
        "port": port,
        "as400": {
            "host": os.getenv("AS400_HOST") or "161.82.146.249",
            "user": os.getenv("AS400_USER", ""),
            "password": os.getenv("AS400_PASSWORD", ""),
            "library": os.getenv("AS400_LIBRARY", "*LIBL")
        }
    }
    
    config_file = config_dir / "agent.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    if foreground:
        # Run in foreground (for containers)
        click.echo("🚀 Starting AS400 Agent in foreground mode...")
        click.echo(f"   Config: {config_file}")
        click.echo(f"   URL: http://{host}:{port}")
        click.echo("   Press Ctrl+C to stop\n")
        
        # Run uvicorn in foreground (blocks)
        import uvicorn
        uvicorn.run(
            "qadmcli_agent.server:app",
            host=host,
            port=port,
            log_level="info"
        )
    else:
        # Run in background (for host)
        click.echo("🚀 Starting AS400 Agent...")
        click.echo(f"   Config: {config_file}")
        click.echo(f"   Log: {LOG_FILE}")
        
        # Start agent as background process
        cmd = [
            sys.executable, "-m", "uvicorn",
            "qadmcli_agent.server:app",
            "--host", host,
            "--port", str(port),
            "--log-level", "info"
        ]
        
        # Launch in background
        with open(LOG_FILE, 'w') as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=Path(__file__).parent.parent
            )
        
        # Save PID
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        
        click.echo(f"   PID: {process.pid}")
        click.echo("   Waiting for agent to start...")
        
        # Wait for agent to be ready
        for i in range(30):
            time.sleep(1)
            try:
                response = requests.get(f"http://{host}:{port}/health", timeout=2)
                if response.status_code == 200:
                    click.echo(f"\n✅ Agent started successfully!")
                    click.echo(f"   URL: http://{host}:{port}")
                    click.echo(f"   Health: http://{host}:{port}/health")
                    click.echo(f"   Status: http://{host}:{port}/status")
                    click.echo(f"\nTo stop: qadmcli agent stop")
                    return
            except:
                pass
            
            if i % 5 == 0:
                click.echo(f"   ... ({i+1}s)")
        
        click.echo("\n❌ Agent failed to start. Check logs:")
        click.echo(f"   tail -f {LOG_FILE}")


@agent.command()
def stop():
    """Stop AS400 Agent Daemon."""
    if not is_agent_running():
        click.echo("⚠️  Agent is not running")
        return
    
    pid = get_agent_pid()
    click.echo(f"🛑 Stopping agent (PID: {pid})...")
    
    try:
        # Send SIGTERM
        os.kill(pid, signal.SIGTERM)
        
        # Wait for process to stop
        for i in range(10):
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                # Process stopped
                break
        else:
            # Force kill if still running
            click.echo("   Force stopping...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
        
        # Clean up PID file
        PID_FILE.unlink(missing_ok=True)
        click.echo("✅ Agent stopped")
        
    except Exception as e:
        click.echo(f"❌ Failed to stop agent: {e}")
        sys.exit(1)


@agent.command()
def status():
    """Check AS400 Agent status."""
    if not is_agent_running():
        click.echo("❌ Agent is not running")
        click.echo(f"\nTo start: qadmcli agent start")
        return
    
    pid = get_agent_pid()
    click.echo(f"✅ Agent is running (PID: {pid})")
    
    # Try to get detailed status from agent
    try:
        response = requests.get(f"http://{AGENT_HOST}:{AGENT_PORT}/status", timeout=2)
        if response.status_code == 200:
            status_data = response.json()
            
            click.echo(f"\n📊 Agent Status:")
            click.echo(f"   Version: {status_data.get('agent_version', 'unknown')}")
            click.echo(f"   JVM: {status_data.get('jvm_status', 'unknown')}")
            click.echo(f"   JT400: {status_data.get('jt400_status', 'unknown')}")
            click.echo(f"   Uptime: {status_data.get('uptime', 'unknown')}")
            
            pool_info = status_data.get('connection_pool')
            if pool_info:
                click.echo(f"\n🔌 Connection Pool:")
                click.echo(f"   Size: {pool_info.get('size', 0)}")
                click.echo(f"   Active: {pool_info.get('active', 0)}")
                click.echo(f"   Idle: {pool_info.get('idle', 0)}")
                click.echo(f"   Total Queries: {pool_info.get('total_queries', 0)}")
                click.echo(f"   Avg Query Time: {pool_info.get('avg_query_time_ms', 0):.2f}ms")
            
            click.echo(f"\n   Health: http://{AGENT_HOST}:{AGENT_PORT}/health")
            click.echo(f"   Status: http://{AGENT_HOST}:{AGENT_PORT}/status")
            
    except requests.exceptions.RequestException:
        click.echo(f"\n⚠️  Agent is running but not responding on port {AGENT_PORT}")
        click.echo(f"   PID: {pid}")


@agent.command()
def logs():
    """View agent logs."""
    if not LOG_FILE.exists():
        click.echo(f"No log file found: {LOG_FILE}")
        return
    
    click.echo(f"📄 Agent logs: {LOG_FILE}\n")
    
    # Show last 50 lines
    with open(LOG_FILE) as f:
        lines = f.readlines()
        for line in lines[-50:]:
            click.echo(line.rstrip())


if __name__ == '__main__':
    agent()
