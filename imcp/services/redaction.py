"""Payload redaction service."""
from typing import Any, Dict, List
import re
import logging
from ._settings import imcp_setting

logger = logging.getLogger(__name__)


class RedactionService:
    """Redact sensitive data from payloads."""

    def __init__(self, patterns: List[str] = None):
        """Initialize with redaction patterns."""
        self.patterns = patterns or imcp_setting("REDACTION_PATTERNS")
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficient matching."""
        self._regex_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.patterns
        ]

    def redact_payload(self, payload: Any) -> Any:
        """Redact sensitive data from payload."""
        if isinstance(payload, dict):
            return self._redact_dict(payload)
        elif isinstance(payload, list):
            return [self.redact_payload(item) for item in payload]
        elif isinstance(payload, str):
            return self._redact_string(payload)
        else:
            return payload

    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Redact dictionary values."""
        redacted = {}
        for key, value in data.items():
            if self._should_redact_key(key):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = self.redact_payload(value)
        return redacted

    def _should_redact_key(self, key: str) -> bool:
        """Check if key should be redacted."""
        key_lower = key.lower()
        for pattern in self._regex_patterns:
            if pattern.search(key_lower):
                return True
        return False

    def _redact_string(self, text: str) -> str:
        """Redact patterns in string values."""
        if len(text) > 20 and any(
            pattern.search(text.lower()) for pattern in self._regex_patterns
        ):
            return "[REDACTED]"
        return text


# Global redaction service
redactor = RedactionService()


def redact_payload(payload: Any) -> Any:
    """Redact sensitive data from payload."""
    return redactor.redact_payload(payload)
