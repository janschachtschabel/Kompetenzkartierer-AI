"""Text as the stores keep it: PostgreSQL's text and jsonb take no NUL, UTF-8 no lone surrogate."""

import re

UNSTORABLE = re.compile(f"[{chr(0)}{chr(0xD800)}-{chr(0xDFFF)}]")
