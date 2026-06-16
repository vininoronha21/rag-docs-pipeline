import re

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_RELATIVE_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!https?://|#|mailto:)([^)]+)\)")


def clean_markdown(content: str) -> str:
    """Normalize Markdown while keeping headings, code fences, and links readable."""
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = _HTML_COMMENT_RE.sub("", content)
    content = _IMAGE_RE.sub(r"\1", content)
    content = _RELATIVE_LINK_RE.sub(r"\1", content)
    content = "\n".join(line.rstrip() for line in content.splitlines())
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", content).strip()


def extract_title(content: str, fallback: str | None = None) -> str | None:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("#").strip()[:255]
    return fallback
