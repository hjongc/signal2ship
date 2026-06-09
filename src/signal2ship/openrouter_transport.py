from __future__ import annotations

import json
import ssl
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.client import HTTPException, HTTPSConnection
from typing import Final, Protocol, override
from urllib.parse import urlparse

import truststore

OPENROUTER_ENDPOINT: Final = "https://openrouter.ai/api/v1/chat/completions"
HTTP_ERROR_STATUS_MIN: Final = 400

type JsonValue = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class SSLContextFactory(Protocol):
    def __call__(self) -> ssl.SSLContext:
        """Build one SSL context for an HTTPS request."""
        ...


class OpenRouterTransport(Protocol):
    def post_json(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str],
        payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> str:
        """Post a JSON request and return the response body."""
        ...


@dataclass(frozen=True, slots=True)
class OpenRouterRequestError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"openrouter request error: {self.detail}"


def _system_ssl_context() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


@dataclass(frozen=True, slots=True)
class UrlLibOpenRouterTransport:
    ssl_context_factory: SSLContextFactory = field(default=_system_ssl_context)

    def post_json(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str],
        payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> str:
        """Post one OpenRouter request through HTTPS."""
        parsed = urlparse(endpoint)
        path = parsed.path
        if parsed.query != "":
            path = f"{path}?{parsed.query}"

        connection = HTTPSConnection(
            parsed.netloc,
            timeout=timeout_seconds,
            context=self.ssl_context_factory(),
        )
        try:
            connection.request(
                "POST",
                path,
                body=json.dumps(payload).encode("utf-8"),
                headers=dict(headers),
            )
            response = connection.getresponse()
            detail = response.read().decode("utf-8", errors="replace")
        except HTTPException as error:
            raise OpenRouterRequestError(
                detail=str(error),
            ) from error
        except ssl.SSLCertVerificationError as error:
            raise OpenRouterRequestError(
                detail=(
                    "TLS certificate verification failed with the system trust "
                    "store. Confirm the corporate or proxy CA is trusted in "
                    f"macOS Keychain. Original error: {error}"
                ),
            ) from error
        except OSError as error:
            raise OpenRouterRequestError(
                detail=f"network transport failed: {error}",
            ) from error
        else:
            if response.status >= HTTP_ERROR_STATUS_MIN:
                raise OpenRouterRequestError(
                    detail=f"HTTP {response.status}: {detail[:500]}",
                )
            return detail
        finally:
            connection.close()
