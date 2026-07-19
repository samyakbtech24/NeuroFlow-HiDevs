from dataclasses import dataclass


@dataclass
class ExtractedPage:
    """
    Represents a single page or block of content extracted from a document.
    page_number: The 1-based page number.
    content: The textual content (or markdown table representation).
    content_type: The type of content, e.g. "text", "table", "image_description".
    metadata: Key-value dictionary containing page-specific metadata (e.g. section headings).
    """
    page_number: int
    content: str
    content_type: str  # "text" | "table" | "image_description"
    metadata: dict  # type: ignore
