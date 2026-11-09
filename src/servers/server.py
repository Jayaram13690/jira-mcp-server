#server.py
import logging

from fastmcp import FastMCP
from starlette.responses import JSONResponse

# Fix for relative import error when running as a script
# project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# sys.path.insert(0, project_root)
from src.tools.jira_tools import register_tools
from src.utils.log_helper import setup_logging  # Import the decorator

# Initialize logging at module level
try:
    setup_logging()
    logger = logging.getLogger("jira-mcp-server")
    logger.debug("Initializing jira MCP server at module level...")
except Exception as e:
    print(f"Logging setup error during initialization: {e}")
    raise


# Create MCP server instance at module level for uvicorn
mcp = FastMCP(name="jira-mcp-server")

# Register tools
logger.info("Registering tools...")
register_tools(mcp)

# Add health check endpoint using Starlette JSONResponse
@mcp.custom_route("/mcp/jira/health", methods=["GET"])
async def health_check(request):
    logger.debug("Health check endpoint called")
    return JSONResponse({"status": "healthy", "service": "jira-mcp-server"})

logger.info("Health check endpoint registered at /mcp/jira/health")

# Create ASGI application using FastMCP's http_app() method - the
# renamed replacement for the older streamable_http_app() this code
# originally used. Confirmed via:
#   uv run python -c "from fastmcp import FastMCP; import inspect; print(inspect.signature(FastMCP.http_app))"
# `path` is a real, valid parameter on the installed version.
mcp_app = mcp.http_app(path="/mcp/jira")

logger.info("FastMCP ASGI application 'mcp_app' created and ready for uvicorn")
logger.info("MCP endpoint will be available at: http://localhost:{port}/mcp/jira")

