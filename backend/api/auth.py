from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.security.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

class TokenRequest(BaseModel):  # type: ignore
    client_id: str
    client_secret: str

@router.post("/token")  # type: ignore
async def generate_token(request: TokenRequest):  # noqa: ANN201  # type: ignore
    # Mocking client credentials for the demo
    if request.client_id == "admin" and request.client_secret == "admin":
        scopes = ["query", "ingest", "admin"]
    elif request.client_id == "user" and request.client_secret == "user":
        scopes = ["query", "ingest"]
    elif request.client_id == "guest" and request.client_secret == "guest":
        scopes = ["query"]
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    token = create_access_token(request.client_id, scopes)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600
    }
