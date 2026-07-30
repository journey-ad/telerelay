"""FastAPI dependencies shared across API routes."""

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from backend.application import ApplicationContext

basic = HTTPBasic(auto_error=False)


def get_context(request: Request) -> ApplicationContext:
    return request.app.state.context


def require_auth(
    credentials: HTTPBasicCredentials | None = Depends(basic),
    context: ApplicationContext = Depends(get_context),
) -> bool:
    expected_username = context.config.web_auth_username
    expected_password = context.config.web_auth_password
    if not expected_username or not expected_password:
        return True
    if credentials is not None:
        username_ok = secrets.compare_digest(credentials.username, expected_username)
        password_ok = secrets.compare_digest(credentials.password, expected_password)
        if username_ok and password_ok:
            return True
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Authentication required"},
        headers={"WWW-Authenticate": "Basic"},
    )

