import time
from typing import Any

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

security = HTTPBearer()

JWT_SECRET = "neuroflow-super-secret-key-1234"
JWT_ALGORITHM = "HS256"

def create_access_token(client_id: str, scopes: list[str], expires_in: int = 3600) -> str:
    payload = {
        "sub": client_id,
        "scopes": scopes,
        "exp": int(time.time()) + expires_in
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)  # type: ignore

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):  # noqa: ANN201  # type: ignore
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def require_scope(required_scope: str):  # noqa: ANN201  # type: ignore
    def scope_checker(user: dict[str, Any] = Depends(get_current_user)):  # noqa: ANN202  # type: ignore
        scopes = user.get("scopes", [])
        if required_scope not in scopes:
            raise HTTPException(status_code=403, detail=f"Missing required scope: {required_scope}")
        return user
    return scope_checker
