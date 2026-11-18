"""HTML → PDF via WeasyPrint (imported lazily; optional dependency, installed in the Docker image)."""

from __future__ import annotations


def render_pdf(html_doc: str) -> bytes | None:
    """PDF bytes, or None when WeasyPrint is not installed (callers then return the HTML)."""
    try:
        from weasyprint import HTML  # type: ignore[import-not-found]
    except Exception:
        return None
    return HTML(string=html_doc).write_pdf()
