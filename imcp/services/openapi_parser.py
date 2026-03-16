"""OpenAPI parser service."""
from typing import Any, Dict, List, Optional
import logging
from prance import ResolvingParser
from openapi_spec_validator import validate_spec

logger = logging.getLogger(__name__)


class OpenAPIMetadata:
    """OpenAPI metadata."""

    def __init__(self, url: str, operations: List[Dict[str, Any]], spec: Dict[str, Any]):
        self.url = url
        self.operations = operations
        self.spec = spec


class OpenAPIParser:
    """OpenAPI parser using prance."""

    def parse_openapi(self, url: str) -> OpenAPIMetadata:
        """Parse OpenAPI specification from URL or file path."""
        try:
            logger.info(f"Parsing OpenAPI spec from {url}")

            # Handle file:// URLs — convert to local path
            parse_url = url
            if url.startswith("file://"):
                parse_url = url.replace("file://", "")
                # Remove leading slash for Windows absolute paths (/C:/ -> C:/)
                if len(parse_url) > 2 and parse_url[0] == "/" and parse_url[2] == ":":
                    parse_url = parse_url[1:]
                logger.info(f"Resolved file path: {parse_url}")

            parser = ResolvingParser(parse_url, backend="openapi-spec-validator")
            spec = parser.specification

            try:
                validate_spec(spec)
                logger.info("OpenAPI spec validation passed")
            except Exception as e:
                logger.warning(f"OpenAPI spec validation warning: {e}")

            operations = self._extract_operations_from_spec(spec)
            logger.info(f"Extracted {len(operations)} operations from OpenAPI spec")
            return OpenAPIMetadata(url=url, operations=operations, spec=spec)

        except Exception as e:
            logger.error(f"Failed to parse OpenAPI spec: {e}")
            raise

    def _extract_operations_from_spec(self, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract all operations from OpenAPI spec."""
        operations = []
        paths = spec.get("paths", {})

        for path, path_item in paths.items():
            for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
                if method not in path_item:
                    continue

                operation = path_item[method]
                operation_id = operation.get("operationId", f"{method}_{path.replace('/', '_')}")

                operations.append(
                    {
                        "name": operation_id,
                        "method": method.upper(),
                        "path": path,
                        "summary": operation.get("summary", ""),
                        "description": operation.get("description", ""),
                        "parameters": operation.get("parameters", []),
                        "requestBody": operation.get("requestBody", {}),
                        "responses": operation.get("responses", {}),
                    }
                )

        return operations

    def extract_operations(
        self,
        openapi_metadata: OpenAPIMetadata,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Filter operations by allowlist/denylist."""
        operations = openapi_metadata.operations

        if denylist:
            operations = [op for op in operations if op["name"] not in denylist]

        if allowlist:
            operations = [op for op in operations if op["name"] in allowlist]

        return operations


# Global parser instance
parser = OpenAPIParser()


def parse_openapi(url: str) -> OpenAPIMetadata:
    """Parse OpenAPI spec."""
    return parser.parse_openapi(url)


def extract_operations(
    openapi_metadata: OpenAPIMetadata,
    allowlist: Optional[List[str]] = None,
    denylist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Extract and filter operations."""
    return parser.extract_operations(openapi_metadata, allowlist, denylist)
