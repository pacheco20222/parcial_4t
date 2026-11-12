from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request

from .logging import event

ROLES = {"Operator": 1, "Supervisor": 2, "Admin": 3}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def identity(request: Request) -> dict[str, Any]:
    token = request.cookies.get("flood_at")
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    try:
        if not token:
            raise jwt.InvalidTokenError()
        claims = jwt.decode(
            token,
            request.app.state.public_key,
            algorithms=["RS256"],
            issuer="flood-ops",
            audience="flood-platform",
            options={"require": ["sub", "email", "role", "amr", "iss", "aud", "exp"]},
        )
        if (
            not isinstance(claims.get("role"), str)
            or claims["role"] not in ROLES
            or claims.get("amr") not in ("pwd", "mfa")
        ):
            raise jwt.InvalidTokenError()
        return claims
    except jwt.InvalidTokenError:
        event("auth.jwt_rejected", client_ip=client_ip(request), path=request.url.path)
        raise HTTPException(401, "Invalid authentication", headers={"WWW-Authenticate": "Bearer"}) from None


def supervisor(request: Request, claims: Annotated[dict[str, Any], Depends(identity)]) -> dict[str, Any]:
    if ROLES[claims["role"]] < ROLES["Supervisor"] or (
        request.app.state.settings.enforce_mfa and claims["amr"] != "mfa"
    ):
        event("auth.jwt_rejected", client_ip=client_ip(request), path=request.url.path)
        raise HTTPException(403, "Supervisor access required")
    return claims
