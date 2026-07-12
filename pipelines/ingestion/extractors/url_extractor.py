import logging
from typing import List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
import trafilatura

from pipelines.ingestion.extractors.extracted_page import ExtractedPage

logger = logging.getLogger("url-extractor")

async def can_fetch(url: str, user_agent: str = "*") -> bool:
    """
    Parses the robots.txt of the domain and checks if the given URL is allowed to be crawled.
    """
    try:
        parsed_url = urlparse(url)
        # Construct robots.txt URL
        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        
        async with httpx.AsyncClient(timeout=3.0) as client:
            headers = {"User-Agent": "NeuroFlowBot/1.0"}
            response = await client.get(robots_url, headers=headers, follow_redirects=True)
            
        # Parse the robots.txt rules
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        
        return parser.can_fetch(user_agent, url)
    except Exception as e:
        logger.warning(f"Error checking robots.txt rules for {url}: {e}. Defaulting to allowed.")
        return True

async def extract_url(url: str) -> List[ExtractedPage]:
    """
    Downloads webpage HTML asynchronously and extracts clean text, tables, and metadata.
    - Respects robots.txt rules.
    - Uses httpx to fetch webpage.
    - Uses trafilatura to extract text (with include_tables=True).
    """
    # 1. Check robots.txt permissions
    allowed = await can_fetch(url)
    if not allowed:
        logger.error(f"Access to URL {url} blocked by robots.txt rules.")
        return [
            ExtractedPage(
                page_number=1,
                content=f"[Access Blocked by robots.txt for URL: {url}]",
                content_type="text",
                metadata={"url": url, "blocked": True}
            )
        ]

    # 2. Fetch the web HTML content
    html_content = ""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"User-Agent": "NeuroFlowBot/1.0"}
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
    except Exception as e:
        logger.error(f"Failed to fetch URL {url}: {e}")
        return []

    # 3. Extract text content and webpage metadata
    try:
        # Extract main text block including html tables formatted
        content = trafilatura.extract(
            html_content,
            include_tables=True,
            output_format="txt"
        ) or ""
        
        # Extract HTML metadata (Title, Author, Date, Canonical URL)
        meta = trafilatura.extract_metadata(html_content)
        metadata = {}
        if meta:
            metadata = {
                "title": getattr(meta, "title", ""),
                "author": getattr(meta, "author", ""),
                "canonical_url": getattr(meta, "canonicalurl", "") or url,
                "publish_date": getattr(meta, "date", "")
            }
        else:
            metadata = {"url": url}
            
    except Exception as e:
        logger.error(f"Trafilatura extraction failed for URL {url}: {e}")
        return []

    if not content.strip():
        logger.warning(f"No content extracted from URL: {url}")
        return []

    return [
        ExtractedPage(
            page_number=1,
            content=content.strip(),
            content_type="text",
            metadata=metadata
        )
    ]
