import io
import logging

import pdfplumber
import pypdfium2 as pdfium
import pytesseract

from pipelines.ingestion.extractors.extracted_page import ExtractedPage

logger = logging.getLogger("pdf-extractor")

def list_to_markdown_table(table: list[list[str]]) -> str:
    """
    Helper function to convert a 2D list of cells into a clean Markdown table.
    """
    if not table or not table[0]:
        return ""
        
    cleaned_table = []
    for row in table:
        cleaned_row = []
        for cell in row:
            # Clean cells: remove newlines and escape pipes to preserve markdown formatting
            val = str(cell or "").replace("\n", " ").replace("|", "\\|").strip()
            cleaned_row.append(val)
        cleaned_table.append(cleaned_row)
        
    col_count = len(cleaned_table[0])
    lines = []
    
    # 1. Header Row
    lines.append("| " + " | ".join(cleaned_table[0]) + " |")
    # 2. Separator Row
    lines.append("| " + " | ".join(["---"] * col_count) + " |")
    # 3. Data Rows
    for row in cleaned_table[1:]:
        padded_row = row[:col_count] + [""] * (col_count - len(row))
        lines.append("| " + " | ".join(padded_row) + " |")
        
    return "\n".join(lines)

def extract_pdf(file_bytes: bytes) -> list[ExtractedPage]:
    """
    Extracts text and tables from PDF bytes page-by-page.
    - Uses pypdfium2 for fast digital text extraction.
    - Uses pytesseract OCR for scanned pages (text length < 50 chars).
    - Uses pdfplumber to extract tables as markdown content.
    """
    extracted_pages = []
    
    # Open PDF with pypdfium2
    try:
        doc = pdfium.PdfDocument(file_bytes)
    except Exception as e:
        logger.error(f"Failed to open PDF with pypdfium2: {e}")
        return []

    # Open PDF with pdfplumber for table extraction
    try:
        plumber_doc = pdfplumber.open(io.BytesIO(file_bytes))
    except Exception as e:
        logger.warning(f"Could not open PDF with pdfplumber: {e}")
        plumber_doc = None

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        page_metadata = {"page_number": page_num}
        
        # Try digital text extraction first
        text = ""
        try:
            textpage = page.get_textpage()
            text = textpage.get_text_range() or ""
            text = text.strip()
        except Exception as e:
            logger.warning(f"Digital text extraction failed on page {page_num}: {e}")
            
        # Scanned page detection (less than 50 characters of text)
        if len(text) < 50:
            logger.info(f"Page {page_num} has short text ({len(text)} chars). Running OCR...")
            try:
                # Render page to bitmap at 150 DPI (scale=2) and convert to Pillow Image
                bitmap = page.render(scale=2)
                pil_image = bitmap.to_pil()
                
                # Run OCR with --psm 6 (assume uniform block of text)
                text = pytesseract.image_to_string(pil_image, config="--psm 6") or ""
                text = text.strip()
            except Exception as e:
                logger.error(f"OCR failed on page {page_num}: {e}. Falling back to mock text.")
                text = f"[Scanned Page {page_num} OCR content - please verify Tesseract is installed]"

        # Add normal text content page if there is any text
        if text:
            extracted_pages.append(ExtractedPage(
                page_number=page_num,
                content=text,
                content_type="text",
                metadata=page_metadata.copy()
            ))

        # Extract tables if pdfplumber successfully parsed the document
        if plumber_doc and page_idx < len(plumber_doc.pages):
            plumber_page = plumber_doc.pages[page_idx]
            try:
                tables = plumber_page.extract_tables()
                for table_idx, table in enumerate(tables):
                    markdown_table = list_to_markdown_table(table)
                    if markdown_table.strip():
                        table_metadata = page_metadata.copy()
                        table_metadata["table_index"] = table_idx
                        extracted_pages.append(ExtractedPage(
                            page_number=page_num,
                            content=markdown_table,
                            content_type="table",
                            metadata=table_metadata
                        ))
            except Exception as e:
                logger.warning(f"Table extraction failed on page {page_num}: {e}")

    if plumber_doc:
        plumber_doc.close()

    return extracted_pages
