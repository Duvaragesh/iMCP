"""WSDL parser service (simplified stub — full Zeep integration is Phase 2)."""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class WSDLMetadata:
    """WSDL metadata."""

    def __init__(self, url: str, operations: List[Dict[str, Any]]):
        self.url = url
        self.operations = operations


class WSDLParser:
    """Simplified WSDL parser."""

    def parse_wsdl(self, url: str) -> WSDLMetadata:
        """Parse WSDL (stub — returns empty operations until Zeep integration)."""
        logger.info(f"Parsing WSDL from {url}")
        return WSDLMetadata(url=url, operations=[])

    def extract_operations(
        self,
        wsdl_metadata: WSDLMetadata,
        allowlist: Optional[List[str]] = None,
        denylist: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Filter operations by allowlist/denylist."""
        operations = wsdl_metadata.operations

        if denylist:
            operations = [op for op in operations if op["name"] not in denylist]

        if allowlist:
            operations = [op for op in operations if op["name"] in allowlist]

        return operations


parser = WSDLParser()


def parse_wsdl(url: str) -> WSDLMetadata:
    """Parse WSDL."""
    return parser.parse_wsdl(url)


def extract_operations(
    wsdl_metadata: WSDLMetadata,
    allowlist: Optional[List[str]] = None,
    denylist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Extract and filter operations."""
    return parser.extract_operations(wsdl_metadata, allowlist, denylist)
