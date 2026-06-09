from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal, Protocol, TypedDict, assert_never, override

from pydantic import Field

from .envfile import DotenvLoadError, load_dotenv_environment
from .models import FrozenModel
from .openrouter_transport import (
    OPENROUTER_ENDPOINT,
    JsonValue,
    OpenRouterRequestError,
    OpenRouterTransport,
    UrlLibOpenRouterTransport,
)

DEFAULT_DOTENV_PATH: Final = Path(".env")
DEFAULT_TIMEOUT_SECONDS: Final = 60.0
DEFAULT_TEMPERATURE: Final = 0.2
DEFAULT_MAX_TOKENS: Final = 900
DEFAULT_APP_TITLE: Final = "Signal2Ship"
FLASH_MODEL_ENV: Final = "OPENROUTER_FLASH_MODEL"
PRO_MODEL_ENV: Final = "OPENROUTER_PRO_MODEL"
LEGACY_MODEL_ENV: Final = "OPENROUTER_MODEL"
LEGACY_PRO_MODEL_ENV: Final = "OPENROUTER_MODEL_PRO"

type OpenRouterModelTier = Literal["flash", "pro"]


class ChatMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_tier: OpenRouterModelTier = "flash",
    ) -> str:
        """Return one completion for a stage prompt."""
        ...


@dataclass(frozen=True, slots=True)
class OpenRouterConfigError(Exception):
    detail: str

    @override
    def __str__(self) -> str:
        return f"openrouter config error: {self.detail}"


class OpenRouterMessage(FrozenModel):
    role: str = Field(min_length=1)
    content: str | None = None


class OpenRouterChoice(FrozenModel):
    message: OpenRouterMessage


class OpenRouterResponse(FrozenModel):
    choices: list[OpenRouterChoice]


@dataclass(frozen=True, slots=True)
class OpenRouterSettings:
    api_key: str
    model: str
    pro_model: str | None = None
    site_url: str | None = None
    app_title: str = DEFAULT_APP_TITLE
    endpoint: str = OPENROUTER_ENDPOINT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def load_openrouter_settings(
    environ: Mapping[str, str] | None = None,
    *,
    model_override: str | None = None,
    dotenv_path: Path | None = None,
) -> OpenRouterSettings:
    source = _settings_source(environ, dotenv_path=dotenv_path)
    api_key = source.get("OPENROUTER_API_KEY", "").strip()
    if api_key == "":
        raise OpenRouterConfigError(detail="missing OPENROUTER_API_KEY")

    model = (
        model_override
        or _optional_env_value(source, FLASH_MODEL_ENV)
        or _optional_env_value(source, LEGACY_MODEL_ENV)
    )
    if model is None or model == "":
        raise OpenRouterConfigError(
            detail=("missing OPENROUTER_FLASH_MODEL, OPENROUTER_MODEL, or --llm-model"),
        )

    pro_model = (
        model_override
        or _optional_env_value(source, PRO_MODEL_ENV)
        or _optional_env_value(source, LEGACY_PRO_MODEL_ENV)
    )
    site_url = source.get("OPENROUTER_SITE_URL")
    app_title = source.get("OPENROUTER_APP_TITLE", DEFAULT_APP_TITLE)
    return OpenRouterSettings(
        api_key=api_key,
        model=model,
        pro_model=pro_model,
        site_url=site_url,
        app_title=app_title,
    )


@dataclass(frozen=True, slots=True)
class OpenRouterClient:
    api_key: str
    model: str
    pro_model: str | None = None
    transport: OpenRouterTransport = field(default_factory=UrlLibOpenRouterTransport)
    site_url: str | None = None
    app_title: str = DEFAULT_APP_TITLE
    endpoint: str = OPENROUTER_ENDPOINT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_tier: OpenRouterModelTier = "flash",
    ) -> str:
        """Call OpenRouter chat completions and return assistant text."""
        payload = _chat_payload(
            self._model_for_tier(model_tier),
            system_prompt,
            user_prompt,
        )
        response_body = self.transport.post_json(
            endpoint=self.endpoint,
            headers=self._headers(),
            payload=payload,
            timeout_seconds=self.timeout_seconds,
        )
        response = OpenRouterResponse.model_validate_json(response_body)
        if len(response.choices) == 0:
            raise OpenRouterRequestError(detail="response contained no choices")

        content = response.choices[0].message.content
        if content is None or content.strip() == "":
            raise OpenRouterRequestError(detail="empty completion content")
        return content.strip()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url is not None and self.site_url.strip() != "":
            headers["HTTP-Referer"] = self.site_url
        if self.app_title.strip() != "":
            headers["X-Title"] = self.app_title
        return headers

    def _model_for_tier(self, model_tier: OpenRouterModelTier) -> str:
        if model_tier == "flash":
            return self.model
        if model_tier == "pro":
            if self.pro_model is None or self.pro_model.strip() == "":
                raise OpenRouterConfigError(
                    detail="missing OPENROUTER_PRO_MODEL for Pro-tier stages",
                )
            return self.pro_model
        assert_never(model_tier)


def build_openrouter_client(
    *,
    model_override: str | None = None,
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = DEFAULT_DOTENV_PATH,
) -> OpenRouterClient:
    settings = load_openrouter_settings(
        environ,
        model_override=model_override,
        dotenv_path=dotenv_path,
    )
    return OpenRouterClient(
        api_key=settings.api_key,
        model=settings.model,
        pro_model=settings.pro_model,
        site_url=settings.site_url,
        app_title=settings.app_title,
        endpoint=settings.endpoint,
        timeout_seconds=settings.timeout_seconds,
    )


def _chat_payload(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, JsonValue]:
    messages: list[JsonValue] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return {
        "model": model,
        "messages": messages,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "stream": False,
    }


def _settings_source(
    environ: Mapping[str, str] | None,
    *,
    dotenv_path: Path | None,
) -> Mapping[str, str]:
    source = os.environ if environ is None else environ
    if dotenv_path is None:
        return source
    try:
        return load_dotenv_environment(source, dotenv_path=dotenv_path)
    except DotenvLoadError as error:
        raise OpenRouterConfigError(detail=f"invalid .env: {error}") from error


def _optional_env_value(source: Mapping[str, str], key: str) -> str | None:
    value = source.get(key, "").strip()
    if value == "":
        return None
    return value
