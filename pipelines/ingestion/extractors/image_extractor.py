import io
import logging

import pytesseract
from PIL import Image

from backend.providers.base import ChatMessage
from backend.providers.client import NeuroFlowClient
from backend.providers.router import RoutingCriteria
from pipelines.ingestion.extractors.extracted_page import ExtractedPage

logger = logging.getLogger("image-extractor")

async def extract_image(file_bytes: bytes, filename: str = "image.png") -> list[ExtractedPage]:
    """
    Extracts content from image bytes.
    1. Loads the image and resizes it to max 1024px on the longest side.
    2. Runs Tesseract OCR to extract any text in the image.
    3. Calls the vision LLM via NeuroFlowClient to get a detailed description.
    4. Combines the description and OCR text.
    """
    try:
        image = Image.open(io.BytesIO(file_bytes))
    except Exception as e:
        logger.error(f"Failed to open image: {e}")
        return []

    # 1. Resize to max 1024px on the longest side
    max_size = 1024
    width, height = image.size
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

    # 2. Run Tesseract OCR for text in the image
    ocr_text = ""
    try:
        ocr_text = pytesseract.image_to_string(image).strip()
    except Exception as e:
        logger.warning(f"pytesseract OCR failed on image: {e}. Falling back to empty OCR.")
        ocr_text = "[Tesseract OCR not installed or failed]"

    # 3. Call the vision LLM using the NeuroFlowClient
    description = ""
    try:
        client = NeuroFlowClient()
        messages = [
            ChatMessage(
                role="user",
                content="Provide a detailed description of the objects, colors, and layout of this image."
            )
        ]
        criteria = RoutingCriteria(task_type="rag_generation", require_vision=True)
        # Call the client
        result = await client.chat(messages, criteria)
        description = result.content
    except Exception as e:
        logger.error(f"Vision LLM description call failed: {e}")
        description = "[Vision description unavailable]"

    # 4. Combine description and OCR text as required
    combined_content = f"{description}\n\nText found in image: {ocr_text}"
    
    return [
        ExtractedPage(
            page_number=1,
            content=combined_content,
            content_type="image_description",
            metadata={
                "filename": filename,
                "width": image.width,
                "height": image.height,
                "has_ocr": bool(ocr_text and ocr_text != "[Tesseract OCR not installed or failed]")
            }
        )
    ]
