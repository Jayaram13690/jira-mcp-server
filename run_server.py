"""
Run the JIRA MCP Server

This script starts the MCP server on the configured port
"""

import os
import subprocess
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get configuration
host = os.getenv("HOST", "0.0.0.0")
port = int(os.getenv("JIRA_PORT"))

print("🚀 Starting JIRA MCP Server...")
print(f"   Host: {host}")
print(f"   Port: {port}")
print(f"   Endpoint: http://localhost:{port}/mcp/jira")
print()

# Run with uvicorn
try:
    subprocess.run(
        [
            sys.executable, "-m", "uvicorn", "src.servers.server:mcp_app",
            "--host", host, "--port", str(port), "--reload",
        ],
        check=False,
    )
except KeyboardInterrupt:
    # Ctrl+C is forwarded to uvicorn, which has already shut down cleanly.
    print("\nJIRA MCP Server stopped.")
