from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {
    "CLOUDOPS_LIVE_AWS_TESTS": "true",
    "EXPECTED_AWS_ACCOUNT_ID": "111122223333",
    "EXPECTED_AWS_REGION": "ap-south-1",
    "EXPECTED_REMEDIATION_ROLE_ARN": "arn:aws:iam::111122223333:role/CloudOpsSandboxRemediationRole",
    "EXPECTED_SANDBOX_TAG": "AllowCloudOpsRemediation=true",
    "EXPLICIT_CONFIRMATION": "RUN-CLOUDOPS-LIVE-AWS-SANDBOX",
    "LIVE_REMEDIATION_ACTION": "s3.enable_public_access_block",
    "EXPECTED_S3_BUCKET": "cloudops-lab-synthetic-example",
    "CLOUDOPS_API_URL": "https://cloudops.example.test",
    "CLOUDOPS_ORGANIZATION_ID": str(uuid.uuid4()),
    "CLOUDOPS_REMEDIATION_REQUEST_ID": str(uuid.uuid4()),
    "CLOUDOPS_AUTH_TOKEN_FILE": "synthetic-token-file",
    "REMEDIATION_EXTERNAL_ID_FILE": "synthetic-external-id-file",
}


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "live_remediation_harness", ROOT / "scripts" / "live_remediation_harness.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in tuple(os.environ):
        if key in REQUIRED or key == "EXECUTION_CONFIRMATION":
            monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)


def test_default_configuration_refuses_without_touching_aws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    for key in REQUIRED:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(module.SafetyRefusal, match="CLOUDOPS_LIVE_AWS_TESTS"):
        module.HarnessConfig.from_environment()


@pytest.mark.parametrize(
    "name",
    (
        "CLOUDOPS_LIVE_AWS_TESTS",
        "EXPECTED_AWS_ACCOUNT_ID",
        "EXPECTED_AWS_REGION",
        "EXPECTED_REMEDIATION_ROLE_ARN",
        "EXPECTED_SANDBOX_TAG",
        "EXPLICIT_CONFIRMATION",
    ),
)
def test_every_mandatory_gate_is_required(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    module = _module()
    _environment(monkeypatch)
    monkeypatch.delenv(name)
    with pytest.raises(module.SafetyRefusal):
        module.HarnessConfig.from_environment()


def test_action_and_resource_are_statically_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    _environment(monkeypatch)
    monkeypatch.setenv("LIVE_REMEDIATION_ACTION", "iam.create_user")
    with pytest.raises(module.SafetyRefusal, match="action_not_allowed"):
        module.HarnessConfig.from_environment()

    _environment(monkeypatch)
    monkeypatch.setenv("EXPECTED_S3_BUCKET", "customer-data")
    with pytest.raises(module.SafetyRefusal, match="s3_bucket_prefix_not_allowed"):
        module.HarnessConfig.from_environment()


def test_execute_requires_a_separate_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    _environment(monkeypatch)
    monkeypatch.delenv("EXECUTION_CONFIRMATION", raising=False)
    with pytest.raises(module.SafetyRefusal, match="separate_execution_confirmation_missing"):
        module.execute_command(type("Args", (), {"plan_file": "missing.json"})())


def test_plan_and_private_files_must_stay_outside_repository(tmp_path: Path) -> None:
    module = _module()
    repository_plan = ROOT / "unsafe-plan.json"
    with pytest.raises(module.SafetyRefusal, match="outside_repository"):
        module._plan_path(str(repository_plan))
    with pytest.raises(module.SafetyRefusal, match="outside_repository"):
        module._read_private_value(ROOT / "unsafe-token", "auth_token")

    external_plan = tmp_path / "reviewed.json"
    assert module._plan_path(str(external_plan)) == external_plan.resolve()


def test_required_tags_and_tenant_are_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    _environment(monkeypatch)
    config = module.HarnessConfig.from_environment()

    class S3:
        def get_bucket_tagging(self, **_kwargs: object) -> dict[str, object]:
            return {"TagSet": []}

    with pytest.raises(module.SafetyRefusal, match="required_remediation_tags_missing"):
        module._verify_resource(config, lambda *_args: S3())


def test_default_client_rejects_root_before_assume_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    _environment(monkeypatch)
    config = module.HarnessConfig.from_environment()

    class RootSTS:
        def get_caller_identity(self) -> dict[str, str]:
            return {
                "Account": config.account_id,
                "Arn": f"arn:aws:iam::{config.account_id}:root",
            }

    class Config:
        def __init__(self, **_kwargs: object) -> None:
            pass

    boto3_module = ModuleType("boto3")
    botocore_module = ModuleType("botocore")
    config_module = ModuleType("botocore.config")
    setattr(boto3_module, "client", lambda *_args, **_kwargs: RootSTS())
    setattr(config_module, "Config", Config)
    monkeypatch.setitem(sys.modules, "boto3", boto3_module)
    monkeypatch.setitem(sys.modules, "botocore", botocore_module)
    monkeypatch.setitem(sys.modules, "botocore.config", config_module)
    with pytest.raises(module.SafetyRefusal, match="root_identity_forbidden"):
        module.default_clients(config)


def test_plan_requires_approved_tenant_scoped_live_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    _environment(monkeypatch)
    config = module.HarnessConfig.from_environment()
    monkeypatch.setattr(module, "_verify_resource", lambda *_args: None)
    monkeypatch.setattr(
        module,
        "_api_request",
        lambda *_args: {
            "status": "approved",
            "execution_mode": "live_aws",
            "dry_run": False,
            "action_key": config.action_key,
            "organization_id": str(config.organization_id),
            "request_snapshot_hash": "a" * 64,
        },
    )

    plan = module.build_plan(config, clients=lambda *_args: object())
    assert plan["account_suffix"] == config.account_id[-4:]
    assert plan["request_id"] == str(config.request_id)
    assert plan["snapshot_hash"] == "a" * 64

    monkeypatch.setattr(
        module,
        "_api_request",
        lambda *_args: {
            "status": "approved",
            "execution_mode": "live_aws",
            "dry_run": False,
            "action_key": config.action_key,
            "organization_id": str(uuid.uuid4()),
        },
    )
    with pytest.raises(module.SafetyRefusal, match="tenant_mismatch"):
        module.build_plan(config, clients=lambda *_args: object())


def test_source_contains_no_direct_mutation_dispatch() -> None:
    source = (ROOT / "scripts" / "live_remediation_harness.py").read_text(encoding="utf-8")
    assert "put_public_access_block" not in source
    assert "revoke_security_group_ingress" not in source
    assert "authorize_security_group_ingress" not in source
    assert "create_user" not in source
    assert "delete_bucket" not in source
    assert "print(token" not in source
    assert "print(external_id" not in source
    assert "print(raw" not in source
