import json
import logging
import re

logger = logging.getLogger("secret-detector")

SECRET_PATTERNS = {
    "aws_access_key": r"AKIA[0-9A-Z]{16}",
    "generic_api_key": r"['\"]?(?:api|secret|token|key|password)['\"]?\s*[:=]\s*['\"][A-Za-z0-9/+]{20,}['\"]",  # noqa: E501
    "private_key": r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    "jwt_token": r"ey[A-Za-z0-9_-]+\.ey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
}

def scan_and_redact(text: str, document_id: str) -> tuple[str, bool]:
    """
    Scans text for secrets, redacts them with [REDACTED], and logs the event.
    Returns (redacted_text, was_redacted).
    """
    if not text:
        return text, False
        
    redacted = False
    redacted_text = text
    
    for pattern_name, pattern_regex in SECRET_PATTERNS.items():
        if re.search(pattern_regex, redacted_text):
            logger.warning(json.dumps({
                "event": "secret_redacted",
                "document_id": document_id,
                "pattern_type": pattern_name
            }))
            redacted_text = re.sub(pattern_regex, "[REDACTED]", redacted_text)
            redacted = True
            
    return redacted_text, redacted
