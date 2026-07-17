import ipaddress
import re
from urllib.parse import urlparse

import bleach
from fastapi import HTTPException


def sanitize_text(text: str) -> str:
    """Strips HTML from all text inputs."""
    if not text:
        return text
    return bleach.clean(text, tags=[], strip=True)  # type: ignore

def validate_url(url: str) -> str:
    """
    Validates URL matches http/https and blocks SSRF attempts
    against localhost or private IP ranges (10.x, 172.16.x, 192.168.x).
    """
    if not re.match(r"^https?://", url):
        raise HTTPException(status_code=400, detail="Invalid URL scheme. Must be http or https.")
    
    parsed = urlparse(url)
    hostname = parsed.hostname
    
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL structure.")
        
    if hostname.lower() in ["localhost", "127.0.0.1", "::1"]:
        raise HTTPException(status_code=400, detail="SSRF Attempt: Localhost access denied.")
        
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback:
            raise HTTPException(status_code=400, detail="SSRF Attempt: Private IP access denied.")
    except ValueError:
        pass
        
    return url

def validate_file_bytes(file_bytes: bytes, filename: str, mime_type: str) -> bool:
    """
    Checks file magic bytes to ensure they match expected format.
    Specifically rejects executables disguised as PDFs.
    """
    if len(file_bytes) < 4:
        raise HTTPException(status_code=400, detail="File too small to validate.")
        
    magic_start = file_bytes[:4]
    
    # Reject MZ (Windows PE) and ELF (Linux) executables immediately
    if magic_start.startswith(b'MZ') or magic_start == b'\x7fELF':
        raise HTTPException(status_code=400, detail="Malicious file detected: Executable bytes found.")  # noqa: E501
        
    if mime_type == "application/pdf":
        if not file_bytes.startswith(b'%PDF'):
            raise HTTPException(status_code=400, detail="File type mismatch: Not a valid PDF document.")  # noqa: E501
            
    return True
