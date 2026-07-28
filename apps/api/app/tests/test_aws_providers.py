from __future__ import annotations

import json
from typing import Any

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.stub import Stubber  # type: ignore[import-untyped]
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.models.enums import AITaskType, NotificationChannel
from app.services.ai_provider import (
    AIProviderError,
    BedrockAIProvider,
    ProviderErrorCode,
    ProviderExecutionControl,
)
from app.services.notification_provider import (
    NotificationDeliveryOutcome,
    SESNotificationProvider,
)


def _settings(**updates: object) -> Settings:
    values: dict[str, Any] = {
        "app_env": "testing",
        "database_url": SecretStr("sqlite://"),
        "jwt_secret_key": SecretStr("x" * 32),
    }
    values.update(updates)
    return Settings.model_validate(values)


def _client(service: str, region: str = "us-east-1") -> Any:
    return boto3.client(
        service,
        region_name=region,
        aws_access_key_id="synthetic",
        aws_secret_access_key="synthetic",
        aws_session_token="synthetic",
    )


def test_bedrock_converse_returns_valid_bounded_advisory() -> None:
    client = _client("bedrock-runtime")
    content = {
        "title": "Finding explanation",
        "summary": "A deterministic finding requires review.",
        "details": ["Review the persisted evidence."],
        "caveats": ["This is advisory only."],
        "source_references": ["finding:synthetic"],
        "draft_only": True,
    }
    with Stubber(client) as stubber:
        stubber.add_response(
            "converse",
            {
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [{"text": json.dumps(content)}],
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30},
                "metrics": {"latencyMs": 5},
            },
        )
        provider = BedrockAIProvider(
            _settings(
                ai_provider="bedrock",
                aws_bedrock_enabled=True,
                aws_bedrock_model_id="synthetic.model-v1",
            ),
            client,
        )
        result = provider.generate(
            AITaskType.EXPLAIN_FINDING,
            {
                "sources": [
                    {
                        "reference": "finding:synthetic",
                        "evidence": {"password": "synthetic-secret-sentinel"},
                    }
                ]
            },
            ProviderExecutionControl(5),
        )
    assert result.draft_only is True
    assert result.source_references == ["finding:synthetic"]
    assert "synthetic-secret-sentinel" not in result.model_dump_json()


def test_bedrock_throttling_is_retryable_and_sanitized() -> None:
    client = _client("bedrock-runtime")
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "converse",
            service_error_code="ThrottlingException",
            service_message="synthetic-secret-sentinel",
            http_status_code=429,
        )
        provider = BedrockAIProvider(
            _settings(
                ai_provider="bedrock",
                aws_bedrock_enabled=True,
                aws_bedrock_model_id="synthetic.model-v1",
            ),
            client,
        )
        with pytest.raises(AIProviderError) as captured:
            provider.generate(
                AITaskType.EXECUTIVE_SUMMARY,
                {"sources": []},
                ProviderExecutionControl(5),
            )
    assert captured.value.code == ProviderErrorCode.RETRYABLE
    assert captured.value.retryable is True
    assert "synthetic-secret-sentinel" not in str(captured.value)


def test_bedrock_and_ses_production_configuration_fail_closed() -> None:
    base: dict[str, Any] = {
        "app_env": "production",
        "database_url": SecretStr("postgresql://synthetic.invalid/cloudops"),
        "jwt_secret_key": SecretStr("x" * 32),
        "cookie_secure": True,
        "cors_allowed_origins": "https://cloudops.example.invalid",
    }
    with pytest.raises((ValidationError, ValueError), match="AWS_BEDROCK"):
        Settings.model_validate({**base, "ai_provider": "bedrock"})
    with pytest.raises((ValidationError, ValueError), match="AWS_SES"):
        Settings.model_validate({**base, "notification_provider": "ses"})


def test_ses_v2_send_email_records_only_provider_message_id() -> None:
    client = _client("sesv2")
    expected = {
        "FromEmailAddress": "CloudOps <sender@example.com>",
        "Destination": {"ToAddresses": ["recipient@example.com"]},
        "Content": {
            "Simple": {
                "Subject": {"Data": "Synthetic finding", "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": "Synthetic body", "Charset": "UTF-8"}
                },
            }
        },
        "ReplyToAddresses": ["reply@example.com"],
        "ConfigurationSetName": "synthetic-config",
    }
    with Stubber(client) as stubber:
        stubber.add_response(
            "send_email",
            {"MessageId": "synthetic-provider-message-id"},
            expected,
        )
        provider = SESNotificationProvider(
            _settings(
                notification_provider="ses",
                aws_ses_enabled=True,
                aws_ses_from_email="sender@example.com",
                aws_ses_from_name="CloudOps",
                aws_ses_reply_to="reply@example.com",
                aws_ses_configuration_set="synthetic-config",
            ),
            client,
        )
        result = provider.deliver(
            channel=NotificationChannel.EMAIL,
            destination_reference=None,
            recipients=["recipient@example.com"],
            subject="Synthetic finding",
            text_body="Synthetic body",
            template_key="finding",
            context={},
        )
    assert result.outcome == NotificationDeliveryOutcome.SUCCESS
    assert result.provider_message_id == "synthetic-provider-message-id"
    assert "recipient@example.com" not in str(result)


def test_ses_rejects_headers_and_classifies_throttling_without_leakage() -> None:
    settings = _settings(
        notification_provider="ses",
        aws_ses_enabled=True,
        aws_ses_from_email="sender@example.com",
    )
    provider = SESNotificationProvider(settings, _client("sesv2"))
    rejected = provider.deliver(
        channel=NotificationChannel.EMAIL,
        destination_reference=None,
        recipients=["recipient@example.com"],
        subject="Synthetic\r\nBcc: another@example.com",
        text_body="Synthetic body",
        template_key="finding",
        context={},
    )
    assert rejected.error_code == "ses_header_injection"

    client = _client("sesv2")
    with Stubber(client) as stubber:
        stubber.add_client_error(
            "send_email",
            service_error_code="TooManyRequestsException",
            service_message="synthetic-secret-sentinel",
            http_status_code=429,
        )
        throttled = SESNotificationProvider(settings, client).deliver(
            channel=NotificationChannel.EMAIL,
            destination_reference=None,
            recipients=["recipient@example.com"],
            subject="Synthetic",
            text_body="Synthetic body",
            template_key="finding",
            context={},
        )
    assert throttled.retryable is True
    assert throttled.error_code == "ses_transient_failure"
    assert "synthetic-secret-sentinel" not in str(throttled)
