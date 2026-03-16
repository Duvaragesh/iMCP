"""XSD to JSON Schema converter."""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class SchemaConverter:
    """Convert XSD types to JSON Schema format."""

    TYPE_MAPPING = {
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "long": "integer",
        "short": "integer",
        "byte": "integer",
        "decimal": "number",
        "float": "number",
        "double": "number",
        "boolean": "boolean",
        "date": "string",
        "dateTime": "string",
        "time": "string",
        "duration": "string",
        "anyURI": "string",
        "QName": "string",
        "NOTATION": "string",
        "base64Binary": "string",
        "hexBinary": "string",
    }

    def xsd_to_json_schema(self, xsd_type: Any, type_name: str = "root") -> Dict[str, Any]:
        """Convert XSD type to JSON Schema."""
        try:
            if xsd_type is None:
                return {"type": "null"}

            type_str = str(getattr(xsd_type, "name", str(xsd_type)))

            if any(t in type_str for t in self.TYPE_MAPPING.keys()):
                return self._convert_primitive(type_str)

            if hasattr(xsd_type, "elements"):
                return self._convert_complex_type(xsd_type)

            if hasattr(xsd_type, "item_type"):
                return self._convert_array_type(xsd_type)

            logger.warning(f"Unknown type {type_str}, defaulting to string")
            return {"type": "string"}

        except Exception as e:
            logger.error(f"Error converting XSD type {type_name}: {e}")
            return {"type": "object"}

    def _convert_primitive(self, type_str: str) -> Dict[str, Any]:
        """Convert primitive XSD type to JSON Schema."""
        for xsd_type, json_type in self.TYPE_MAPPING.items():
            if xsd_type in type_str.lower():
                schema = {"type": json_type}
                if "date" in type_str.lower():
                    schema["format"] = "date-time" if "time" in type_str.lower() else "date"
                return schema
        return {"type": "string"}

    def _convert_complex_type(self, xsd_type: Any) -> Dict[str, Any]:
        """Convert complex XSD type (object) to JSON Schema."""
        schema: Dict[str, Any] = {"type": "object", "properties": {}}
        required_fields: List[str] = []

        if hasattr(xsd_type, "elements"):
            for element in xsd_type.elements:
                field_name = element[0]
                field_type = element[1].type
                schema["properties"][field_name] = self.xsd_to_json_schema(field_type, field_name)
                if hasattr(element[1], "min_occurs") and element[1].min_occurs > 0:
                    required_fields.append(field_name)

        if required_fields:
            schema["required"] = required_fields

        return schema

    def _convert_array_type(self, xsd_type: Any) -> Dict[str, Any]:
        """Convert array/sequence XSD type to JSON Schema."""
        return {
            "type": "array",
            "items": self.xsd_to_json_schema(xsd_type.item_type, "array_item"),
        }


# Global converter instance
converter = SchemaConverter()


def xsd_to_json_schema(xsd_type: Any, type_name: str = "root") -> Dict[str, Any]:
    """Convert XSD type to JSON Schema."""
    return converter.xsd_to_json_schema(xsd_type, type_name)


def openapi_params_to_json_schema(
    parameters: List[Dict[str, Any]],
    request_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convert OpenAPI parameters and requestBody to JSON Schema for MCP inputSchema."""
    properties = {}
    required = []

    for param in parameters or []:
        param_name = param.get("name")
        if not param_name:
            continue

        param_schema = param.get("schema", {}).copy()
        if "description" in param:
            param_schema["description"] = param["description"]

        properties[param_name] = param_schema

        if param.get("required", False):
            required.append(param_name)

    if request_body:
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        body_schema = json_content.get("schema", {})

        if "properties" in body_schema:
            for prop_name, prop_schema in body_schema["properties"].items():
                properties[prop_name] = prop_schema
            if "required" in body_schema:
                required.extend(body_schema["required"])

        if request_body.get("required", False) and body_schema.get("properties"):
            for prop_name in body_schema.get("properties", {}).keys():
                if prop_name not in required:
                    required.append(prop_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required if required else [],
    }
