"""MCP JSON parser service for direct tool import."""
from typing import Any, Dict, List, Optional
import json
import logging
import httpx

logger = logging.getLogger(__name__)


class MCPJsonMetadata:
    """MCP JSON metadata container."""

    def __init__(
        self,
        url: str,
        name: str,
        version: str,
        description: str,
        tools: List[Dict[str, Any]],
        examples: Optional[List[Dict[str, Any]]] = None,
    ):
        self.url = url
        self.name = name
        self.version = version
        self.description = description
        self.tools = tools
        self.examples = examples or []


class MCPJsonParser:
    """Parser for MCP JSON tool definition files."""

    def parse_mcp_json(self, url: str) -> MCPJsonMetadata:
        """Parse MCP JSON file and extract tool definitions."""
        try:
            logger.info(f"Parsing MCP JSON from {url}")
            content = self._load_json_content(url)
            self._validate_required_fields(content)

            tools = content["tools"]
            self._validate_tools(tools)

            logger.info(f"Successfully parsed MCP JSON with {len(tools)} tools")
            return MCPJsonMetadata(
                url=url,
                name=content["name"],
                version=content["version"],
                description=content.get("description", ""),
                tools=tools,
                examples=content.get("examples", []),
            )

        except Exception as e:
            logger.error(f"Failed to parse MCP JSON: {e}")
            raise

    def _load_json_content(self, url: str) -> Dict[str, Any]:
        """Load JSON content from file or URL."""
        if url.startswith("file://"):
            file_path = url.replace("file://", "")
            if len(file_path) > 2 and file_path[0] == "/" and file_path[2] == ":":
                file_path = file_path[1:]
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        elif url.startswith(("http://", "https://")):
            response = httpx.get(url, timeout=30.0)
            response.raise_for_status()
            return response.json()
        else:
            with open(url, "r", encoding="utf-8") as f:
                return json.load(f)

    def _validate_required_fields(self, content: Dict[str, Any]) -> None:
        """Validate required root-level fields."""
        for field in ["name", "version", "tools"]:
            if field not in content:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(content["tools"], list):
            raise ValueError("'tools' must be an array")

        if len(content["tools"]) == 0:
            raise ValueError("'tools' array cannot be empty")

    def _validate_tools(self, tools: List[Dict[str, Any]]) -> None:
        """Validate tool definitions."""
        for i, tool in enumerate(tools):
            if "name" not in tool:
                raise ValueError(f"Tool at index {i} missing required field: name")
            if "description" not in tool:
                raise ValueError(f"Tool '{tool.get('name', 'unknown')}' missing required field: description")
            if "inputSchema" not in tool:
                raise ValueError(f"Tool '{tool['name']}' missing required field: inputSchema")

            input_schema = tool["inputSchema"]
            if not isinstance(input_schema, dict):
                raise ValueError(f"Tool '{tool['name']}' inputSchema must be an object")
            if "type" not in input_schema:
                raise ValueError(f"Tool '{tool['name']}' inputSchema missing 'type' field")

            if "endpoint" in tool:
                self._validate_endpoint(tool["name"], tool["endpoint"])

    def _validate_endpoint(self, tool_name: str, endpoint: Dict[str, Any]) -> None:
        """Validate endpoint structure."""
        for field in ["method", "path", "baseUrl"]:
            if field not in endpoint:
                raise ValueError(f"Tool '{tool_name}' endpoint missing required field: {field}")

        valid_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
        if endpoint["method"].upper() not in valid_methods:
            raise ValueError(f"Tool '{tool_name}' endpoint has invalid method: {endpoint['method']}")

    def extract_tools(
        self,
        mcp_json_metadata: MCPJsonMetadata,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Filter tools by allowlist/denylist."""
        tools = mcp_json_metadata.tools

        if denylist:
            tools = [tool for tool in tools if tool["name"] not in denylist]
            logger.info(f"Applied denylist, {len(tools)} tools remaining")

        if allowlist:
            tools = [tool for tool in tools if tool["name"] in allowlist]
            logger.info(f"Applied allowlist, {len(tools)} tools remaining")

        return tools


# Global parser instance
parser = MCPJsonParser()


def parse_mcp_json(url: str) -> MCPJsonMetadata:
    """Parse MCP JSON file."""
    return parser.parse_mcp_json(url)


def extract_tools(
    mcp_json_metadata: MCPJsonMetadata,
    allowlist: Optional[List[str]] = None,
    denylist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Extract and filter tools."""
    return parser.extract_tools(mcp_json_metadata, allowlist, denylist)
