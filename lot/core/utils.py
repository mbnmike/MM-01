import json

from django.utils.safestring import mark_safe


def json_ld(data):
    """Serialize schema.org data for a <script type="application/ld+json"> block."""
    text = json.dumps(data, ensure_ascii=False)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return mark_safe(text)
