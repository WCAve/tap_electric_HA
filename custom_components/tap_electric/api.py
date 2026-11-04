"""Async client for the Tap Electric private app API.

Auth model (mirrors the app):
- Log in with the LEGACY Firebase endpoint `relyingparty/verifyPassword`, which
  returns a refresh token directly and does NOT trip the 2FA blocking function
  that the modern `accounts:signInWithPassword` endpoint hits.
- Refresh short-lived idTokens via securetoken.
- If a refresh token is ever rejected (revoked/expired), transparently log in
  again with the stored credentials.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_BASE,
    APP_VERSION,
    FIREBASE_API_KEY,
    GATEWAY_KEY,
    TENANT_ID,
    TOKEN_URL,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

# Legacy endpoint the Tap app uses (bypasses the 2FA blocking function).
VERIFY_PASSWORD_URL = (
    "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword"
)


class TapAuthError(Exception):
    """Credentials / token rejected."""


class TapTwoFactorRequired(TapAuthError):
    """Login was blocked by a 2FA challenge."""


class TapApiError(Exception):
    """Any non-auth API/connection failure."""


def _find_profile_id(obj: Any) -> str | None:
    if isinstance(obj, str):
        return obj if obj.startswith("usr_") else None
    if isinstance(obj, dict):
        for value in obj.values():
            found = _find_profile_id(value)
            if found:
                return found
    if isinstance(obj, list):
        for item in obj:
            found = _find_profile_id(item)
            if found:
                return found
    return None


class TapElectricClient:
    """Handles login, token refresh and authenticated GETs."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        email: str | None = None,
        password: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._refresh_token = refresh_token
        self._id_token: str | None = None
        self._expires_at: float = 0.0
        self.profile_id: str | None = None
        self.account_label: str | None = email

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    async def _login(self) -> None:
        if not (self._email and self._password):
            raise TapAuthError("no credentials available to log in")
        try:
            async with self._session.post(
                VERIFY_PASSWORD_URL,
                params={"key": FIREBASE_API_KEY},
                json={
                    "email": self._email,
                    "password": self._password,
                    "returnSecureToken": True,
                },
            ) as resp:
                body = await resp.text()
                status = resp.status
        except aiohttp.ClientError as err:
            raise TapApiError(f"login connection error: {err}") from err

        if status != 200:
            message = body[:200]
            try:
                message = json.loads(body).get("error", {}).get("message", message)
            except (ValueError, AttributeError):
                pass
            upper = message.upper()
            if "2FA" in upper or "BLOCKING_FUNCTION" in upper or "SECOND" in upper:
                raise TapTwoFactorRequired(message)
            raise TapAuthError(f"login failed ({status}): {message}")

        data = json.loads(body)
        self._refresh_token = data.get("refreshToken")
        self._id_token = data["idToken"]
        self._expires_at = time.time() + int(data.get("expiresIn", 3600)) - 60

    async def _refresh_via_token(self) -> None:
        if not self._refresh_token:
            raise TapAuthError("no refresh token")
        try:
            async with self._session.post(
                TOKEN_URL,
                params={"key": FIREBASE_API_KEY},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
            ) as resp:
                body = await resp.text()
                status = resp.status
        except aiohttp.ClientError as err:
            raise TapApiError(f"token refresh connection error: {err}") from err

        if status != 200:
            raise TapAuthError(f"token refresh failed ({status}): {body[:200]}")

        data = json.loads(body)
        self._id_token = data["id_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]

    async def _ensure_token(self) -> None:
        if self._id_token and time.time() < self._expires_at:
            return
        try:
            await self._refresh_via_token()
        except TapAuthError:
            # No/stale refresh token -> fall back to a full login if we can.
            if self._email and self._password:
                await self._login()
            else:
                raise

    def _headers(self) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self._id_token}",
            "x-api-key": GATEWAY_KEY,
            "x-app-version": APP_VERSION,
            "x-tenant-id": TENANT_ID,
            "user-agent": USER_AGENT,
            "accept-encoding": "gzip",
        }
        if self.profile_id:
            headers["x-profile-id"] = self.profile_id
        return headers

    async def _get(self, path: str) -> Any:
        await self._ensure_token()
        url = f"{API_BASE}{path}"
        try:
            async with self._session.get(url, headers=self._headers()) as resp:
                body = await resp.text()
                status = resp.status
            if status == 401:
                self._id_token = None
                await self._ensure_token()
                async with self._session.get(url, headers=self._headers()) as resp:
                    body = await resp.text()
                    status = resp.status
        except aiohttp.ClientError as err:
            raise TapApiError(f"GET {path} connection error: {err}") from err

        if status == 401:
            raise TapAuthError(f"GET {path} unauthorized: {body[:200]}")
        if status != 200:
            raise TapApiError(f"GET {path} -> {status}: {body[:200]}")
        return json.loads(body)

    async def async_fetch_account(self) -> None:
        try:
            data = await self._get("/3.0/user")
        except (TapApiError, TapAuthError):
            return
        pid = _find_profile_id(data)
        if pid:
            self.profile_id = pid
        if isinstance(data, dict):
            self.account_label = (
                data.get("email")
                or data.get("name")
                or data.get("first_name")
                or self.account_label
            )

    async def async_get_home(self) -> dict[str, Any]:
        data = await self._get("/4.0/home")
        if not isinstance(data, dict):
            raise TapApiError("unexpected home payload")
        return data

    async def async_validate(self) -> None:
        await self._ensure_token()
        await self.async_fetch_account()
        await self.async_get_home()
