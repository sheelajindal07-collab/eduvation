"""POST /auth/sign-up, POST /auth/sign-in — thin wrapper over Supabase
Auth, which already underlies every RLS policy in this schema
(`auth.users`, `auth.uid()`).

Real minor accounts stay out of scope here (docs/SECURITY.md: disabled
until the consent and safeguarding workflow is built and reviewed by a
person — tasks/BCI-004.md). This route does not enforce an age check
itself; that gate belongs to a later, deliberately separate task, not a
side effect of shipping sign-up.

Each call gets a fresh client (app/db/client.py) — never shared, never
cached, per the concurrency fix in docs/DECISIONS.md.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.db import get_anon_client

router = APIRouter(prefix="/auth", tags=["auth"])


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


class SignInRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    user_id: str


@router.post("/sign-up", response_model=AuthResponse, status_code=201)
def sign_up(request: SignUpRequest) -> AuthResponse:
    client = get_anon_client()
    try:
        result = client.auth.sign_up({"email": request.email, "password": request.password})
    except Exception as exc:
        # Supabase Auth errors (weak password, email already registered,
        # ...) surface as their own exception types we don't need to
        # enumerate here — the message itself is safe to relay, it's
        # already user-facing text from the auth provider.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.session is None or result.user is None:
        # Email confirmation is required by the project's Auth settings
        # — not an error, just no session yet.
        raise HTTPException(
            status_code=202,
            detail="Account created. Check your email to confirm before signing in.",
        )
    return AuthResponse(access_token=result.session.access_token, user_id=result.user.id)


@router.post("/sign-in", response_model=AuthResponse)
def sign_in(request: SignInRequest) -> AuthResponse:
    client = get_anon_client()
    try:
        result = client.auth.sign_in_with_password(
            {"email": request.email, "password": request.password}
        )
    except Exception as exc:
        # Never distinguish "no such email" from "wrong password" in the
        # response — that distinction is an account-enumeration leak.
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc

    if result.session is None or result.user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return AuthResponse(access_token=result.session.access_token, user_id=result.user.id)
