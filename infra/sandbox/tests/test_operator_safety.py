from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "aws_sandbox", ROOT / "scripts" / "aws_sandbox.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(**updates: object) -> Namespace:
    values: dict[str, object] = {
        "expected_account_id": "111122223333",
        "region": "ap-south-1",
        "profile": "synthetic-sso",
        "state_owner": "cloudops-platform",
        "confirmation": "DESTROY-CLOUDOPS-AWS-SANDBOX",
        "plan_file": "sandbox-destroy.tfplan",
        "execute_reviewed_plan": False,
    }
    values.update(updates)
    return Namespace(**values)


def test_identity_validation_rejects_before_calling_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_identity", lambda _profile: pytest.fail("AWS called"))
    with pytest.raises(module.SafetyRefusal, match="exact_expected_account_required"):
        module.verify_identity(_args(expected_account_id="not-an-account"))


def test_root_and_wrong_account_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()
    monkeypatch.setattr(
        module,
        "_identity",
        lambda _profile: {
            "Account": "111122223333",
            "Arn": "arn:aws:iam::111122223333:root",
            "UserId": "synthetic",
        },
    )
    with pytest.raises(module.SafetyRefusal, match="root_identity_forbidden"):
        module.verify_identity(_args())

    monkeypatch.setattr(
        module,
        "_identity",
        lambda _profile: {
            "Account": "999900001111",
            "Arn": "arn:aws:sts::999900001111:assumed-role/Synthetic/session",
            "UserId": "synthetic",
        },
    )
    with pytest.raises(module.SafetyRefusal, match="caller_account_mismatch"):
        module.verify_identity(_args())


def test_destroy_requires_state_owner_and_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    monkeypatch.setattr(module, "verify_identity", lambda _args: {})
    monkeypatch.setattr(module, "_state_owner", lambda: "cloudops-platform")
    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: pytest.fail("mutation run"))

    with pytest.raises(module.SafetyRefusal, match="exact_destroy_confirmation_required"):
        module.destroy(_args(confirmation="wrong"))
    with pytest.raises(module.SafetyRefusal, match="terraform_state_owner_mismatch"):
        module.destroy(_args(state_owner="someone-else"))


def test_destroy_plan_rejects_non_delete_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()

    class Result:
        stdout = json.dumps(
            {
                "resource_changes": [
                    {
                        "address": "aws_vpc.sandbox",
                        "change": {
                            "actions": ["create"],
                            "before": None,
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: Result())
    with pytest.raises(module.SafetyRefusal, match="non_delete_action"):
        module._assert_destroy_plan(Path("synthetic.tfplan"))


def test_destroy_plan_rejects_unowned_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module()

    class Result:
        stdout = json.dumps(
            {
                "resource_changes": [
                    {
                        "address": "aws_iam_user.unapproved",
                        "change": {"actions": ["delete"], "before": {}},
                    }
                ]
            }
        )

    monkeypatch.setattr(module, "_run", lambda *_args, **_kwargs: Result())
    with pytest.raises(module.SafetyRefusal, match="unowned_resource"):
        module._assert_destroy_plan(Path("synthetic.tfplan"))
