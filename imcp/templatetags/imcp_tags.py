"""Custom template tags and filters for iMCP templates."""
import json
from django import template
from django.utils.html import escape

register = template.Library()


@register.filter
def to_json(value):
    """Serialize a Python value to a JSON string safe for use in HTML attributes.

    Uses HTML escaping so the browser decodes entities correctly when reading
    inline onclick arguments or data-* attributes.
    Calls to_dict() on Django model instances automatically.
    """
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    return escape(json.dumps(value, default=str))
