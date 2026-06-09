from __future__ import annotations

import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

import signal2ship.openrouter_transport as transport_module
from signal2ship.llm import (
    OpenRouterClient,
    OpenRouterConfigError,
    load_openrouter_settings,
)
from signal2ship.openrouter_transport import (
    JsonValue,
    OpenRouterRequestError,
    UrlLibOpenRouterTransport,
)


@dataclass(slots=True)
class RecordingTransport:
    response_body: str
    payload: dict[str, JsonValue] | None = None
    headers: Mapping[str, str] | None = None

    def post_json(
        self,
        *,
        endpoint: str,
        headers: Mapping[str, str],
        payload: dict[str, JsonValue],
        timeout_seconds: float,
    ) -> str:
        assert endpoint == "https://openrouter.ai/api/v1/chat/completions"
        assert timeout_seconds == 60.0
        self.headers = headers
        self.payload = payload
        return self.response_body


@dataclass(slots=True)
class CertificateFailingTLSConnection:
    netloc: str
    timeout: float
    context: ssl.SSLContext

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes,
        headers: Mapping[str, str],
    ) -> None:
        assert method == "POST"
        assert path == "/api/v1/chat/completions"
        assert len(body) > 0
        assert "Authorization" in headers
        raise ssl.SSLCertVerificationError

    def close(self) -> None:
        return None


def test_openrouter_client_posts_chat_completion_request() -> None:
    # Given
    transport = RecordingTransport(
        response_body=(
            '{"choices":[{"message":{"role":"assistant","content":"stage note"}}]}'
        ),
    )
    client = OpenRouterClient(
        api_key="test-key",
        model="openai/gpt-5.2",
        transport=transport,
        app_title="Signal2Ship",
        site_url="https://github.com/openai/codex",
    )

    # When
    text = client.complete(
        system_prompt="You are the Opportunity Analyst.",
        user_prompt="Score this evidence.",
        model_tier="flash",
    )

    # Then
    assert text == "stage note"
    assert transport.headers == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/openai/codex",
        "X-Title": "Signal2Ship",
    }
    assert transport.payload == {
        "model": "openai/gpt-5.2",
        "messages": [
            {"role": "system", "content": "You are the Opportunity Analyst."},
            {"role": "user", "content": "Score this evidence."},
        ],
        "temperature": 0.2,
        "max_tokens": 900,
        "stream": False,
    }


def test_openrouter_client_uses_pro_model_for_pro_tier() -> None:
    # Given
    transport = RecordingTransport(
        response_body=(
            '{"choices":[{"message":{"role":"assistant","content":"stage note"}}]}'
        ),
    )
    client = OpenRouterClient(
        api_key="test-key",
        model="deepseek/deepseek-v4-flash",
        pro_model="deepseek/deepseek-v4-pro",
        transport=transport,
    )

    # When
    text = client.complete(
        system_prompt="You are the Opportunity Analyst.",
        user_prompt="Score this evidence.",
        model_tier="pro",
    )

    # Then
    assert text == "stage note"
    assert transport.payload is not None
    assert transport.payload["model"] == "deepseek/deepseek-v4-pro"


def test_openrouter_client_requires_pro_model_for_pro_tier() -> None:
    # Given
    transport = RecordingTransport(
        response_body=(
            '{"choices":[{"message":{"role":"assistant","content":"stage note"}}]}'
        ),
    )
    client = OpenRouterClient(
        api_key="test-key",
        model="deepseek/deepseek-v4-flash",
        transport=transport,
    )

    # When / Then
    with pytest.raises(OpenRouterConfigError, match="OPENROUTER_PRO_MODEL"):
        _ = client.complete(
            system_prompt="system",
            user_prompt="user",
            model_tier="pro",
        )


def test_openrouter_settings_require_api_key_and_model() -> None:
    # Given
    env = {"OPENROUTER_API_KEY": "test-key"}

    # When / Then
    with pytest.raises(OpenRouterConfigError, match="OPENROUTER_MODEL"):
        _ = load_openrouter_settings(env, model_override=None)


def test_openrouter_settings_load_dotenv_when_env_values_are_missing(
    tmp_path: Path,
) -> None:
    # Given
    dotenv_path = tmp_path / ".env"
    _ = dotenv_path.write_text(
        """OPENROUTER_API_KEY=dotenv-key
OPENROUTER_FLASH_MODEL=deepseek/deepseek-v4-flash
OPENROUTER_PRO_MODEL=deepseek/deepseek-v4-pro
OPENROUTER_APP_TITLE=Signal2Ship Local""",
        encoding="utf-8",
    )

    # When
    settings = load_openrouter_settings({}, dotenv_path=dotenv_path)

    # Then
    assert settings.api_key == "dotenv-key"
    assert settings.model == "deepseek/deepseek-v4-flash"
    assert settings.pro_model == "deepseek/deepseek-v4-pro"
    assert settings.app_title == "Signal2Ship Local"


def test_openrouter_settings_prefers_explicit_env_over_dotenv(tmp_path: Path) -> None:
    # Given
    dotenv_path = tmp_path / ".env"
    _ = dotenv_path.write_text(
        """OPENROUTER_API_KEY=dotenv-key
OPENROUTER_FLASH_MODEL=deepseek/deepseek-v4-flash
OPENROUTER_PRO_MODEL=deepseek/deepseek-v4-pro""",
        encoding="utf-8",
    )
    env = {
        "OPENROUTER_API_KEY": "env-key",
        "OPENROUTER_FLASH_MODEL": "deepseek/deepseek-v4-flash",
        "OPENROUTER_PRO_MODEL": "openai/gpt-5.2",
    }

    # When
    settings = load_openrouter_settings(env, dotenv_path=dotenv_path)

    # Then
    assert settings.api_key == "env-key"
    assert settings.model == "deepseek/deepseek-v4-flash"
    assert settings.pro_model == "openai/gpt-5.2"


def test_openrouter_model_override_pins_default_and_pro_models() -> None:
    # Given
    env = {
        "OPENROUTER_API_KEY": "env-key",
        "OPENROUTER_FLASH_MODEL": "deepseek/deepseek-v4-flash",
        "OPENROUTER_PRO_MODEL": "deepseek/deepseek-v4-pro",
    }

    # When
    settings = load_openrouter_settings(env, model_override="openai/gpt-5.2")

    # Then
    assert settings.model == "openai/gpt-5.2"
    assert settings.pro_model == "openai/gpt-5.2"


def test_openrouter_client_rejects_empty_response_content() -> None:
    # Given
    transport = RecordingTransport(
        response_body='{"choices":[{"message":{"role":"assistant","content":""}}]}',
    )
    client = OpenRouterClient(
        api_key="test-key",
        model="openai/gpt-5.2",
        transport=transport,
    )

    # When / Then
    with pytest.raises(OpenRouterRequestError, match="empty completion"):
        _ = client.complete(system_prompt="system", user_prompt="user")


def test_url_lib_transport_reports_tls_failure_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(
        transport_module,
        "HTTPSConnection",
        CertificateFailingTLSConnection,
    )
    transport = UrlLibOpenRouterTransport(ssl_context_factory=lambda: ssl_context)

    # When / Then
    with pytest.raises(OpenRouterRequestError) as error:
        _ = transport.post_json(
            endpoint="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": "Bearer sk-or-secret",
                "Content-Type": "application/json",
            },
            payload={
                "model": "deepseek/deepseek-v4-pro",
                "messages": [{"role": "user", "content": "hello"}],
            },
            timeout_seconds=60.0,
        )

    detail = str(error.value)
    assert "TLS certificate verification failed" in detail
    assert "system trust store" in detail
    assert "sk-or-secret" not in detail
