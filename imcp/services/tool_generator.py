"""MCP tool generator service."""
from typing import Any, Dict, List
import logging
from .wsdl_parser import WSDLMetadata
from .schema_converter import xsd_to_json_schema
from .cache import get_cached_tools, set_cached_tools

logger = logging.getLogger(__name__)


class MCPTool:
    """MCP tool definition."""

    def __init__(self, name: str, description: str, input_schema: Dict[str, Any]):
        self.name = name
        self.description = description
        self.inputSchema = input_schema

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }


class ToolGenerator:
    """Generate MCP tools from WSDL/OpenAPI."""

    def generate_mcp_tools(
        self,
        service_id: str,
        wsdl_metadata: WSDLMetadata,
        use_cache: bool = True,
    ) -> List[MCPTool]:
        """Generate MCP tools from WSDL/OpenAPI metadata."""
        if use_cache:
            cached = get_cached_tools(service_id)
            if cached:
                logger.info(f"Returning cached tools for service {service_id}")
                return [
                    MCPTool(
                        name=tool["name"],
                        description=tool["description"],
                        input_schema=tool["inputSchema"],
                    )
                    for tool in cached
                ]

        tools = []
        for operation in wsdl_metadata.operations:
            tool = self._create_tool_from_operation(operation)
            tools.append(tool)

        if use_cache:
            set_cached_tools(service_id, [tool.to_dict() for tool in tools])

        logger.info(f"Generated {len(tools)} tools for service {service_id}")
        return tools

    def _create_tool_from_operation(self, operation: Dict[str, Any]) -> MCPTool:
        """Create MCP tool from WSDL or OpenAPI operation."""
        name = operation["name"]
        description = (
            operation.get("documentation")
            or operation.get("description")
            or f"Execute {name} operation"
        )

        if "parameters" in operation or "requestBody" in operation:
            from .schema_converter import openapi_params_to_json_schema
            input_schema = openapi_params_to_json_schema(
                operation.get("parameters", []),
                operation.get("requestBody"),
            )
        else:
            input_type = operation.get("input", {}).get("type")
            if input_type:
                input_schema = xsd_to_json_schema(input_type, name)
            else:
                input_schema = {"type": "object", "properties": {}}

        description = self._enrich_description(name, description, input_schema)
        return MCPTool(name=name, description=description, input_schema=input_schema)

    def _enrich_description(
        self, name: str, description: str, input_schema: Dict[str, Any]
    ) -> str:
        """Append LLM-guidance hints to tool descriptions based on schema shape."""
        props = input_schema.get("properties", {})

        # Tools that accept a sqlFile + userInputs (template variable substitution pattern)
        if "sqlFile" in props and "userInputs" in props:
            description = (
                f"{description}\n\n"
                "IMPORTANT: SQL files use {{VARIABLE}} placeholders. "
                "You MUST call getSqlVariables first with the chosen sqlFile to discover "
                "which variables are required, then pass them as userInputs "
                "(e.g. {{\"LOGICAL_PARTITION\": \"GLOBALDV\"}}). "
                "Do NOT put variable values in filterByCondition — "
                "filterByCondition is only for extra SQL WHERE clauses."
            )

        # Tools that accept a sqlFile for inspection only
        elif "sqlFile" in props and "userInputs" not in props:
            description = (
                f"{description}\n\n"
                "Use this to inspect a SQL file before calling executeSql. "
                "Returns the raw SQL with {{VARIABLE}} placeholders visible."
            )

        return description


# Global generator
generator = ToolGenerator()


def generate_mcp_tools(
    service_id: str, wsdl_metadata: WSDLMetadata, use_cache: bool = True
) -> List[MCPTool]:
    """Generate MCP tools."""
    return generator.generate_mcp_tools(service_id, wsdl_metadata, use_cache)
