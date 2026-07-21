import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings

admin_bearer = HTTPBearer(auto_error=False)


def require_admin(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(admin_bearer)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    token = credentials.credentials if credentials is not None else ""
    secret = settings.admin_secret
    if not secret.strip() or not secrets.compare_digest(token, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
