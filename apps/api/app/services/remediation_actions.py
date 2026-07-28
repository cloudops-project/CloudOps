from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RemediationAction:
    """A deterministic remediation capability.

    The registry contains data and policy only. It deliberately contains no
    dynamic module names, boto3 method names, shell commands, or user-provided
    instructions.
    """

    key: str
    version: int
    rule_keys: frozenset[str]
    title: str
    preview_steps: tuple[str, ...]
    verification_steps: tuple[str, ...]
    rollback_steps: tuple[str, ...]
    timeout_seconds: int = 30
    max_attempts: int = 3


class RemediationActionRegistry:
    def __init__(self, actions: tuple[RemediationAction, ...]) -> None:
        self._by_key = {action.key: action for action in actions}
        self._by_rule = {
            rule_key: action for action in actions for rule_key in action.rule_keys
        }
        if len(self._by_key) != len(actions):
            raise ValueError("Remediation action keys must be unique")

    def for_rule(self, rule_key: str) -> RemediationAction | None:
        return self._by_rule.get(rule_key)

    def get(self, action_key: str) -> RemediationAction | None:
        return self._by_key.get(action_key)


DEFAULT_REMEDIATION_ACTIONS = (
    RemediationAction(
        key="s3.enable_public_access_block",
        version=1,
        rule_keys=frozenset({"S3_BUCKET_PUBLIC_ACCESS_BLOCK_INCOMPLETE"}),
        title="Enable all S3 Block Public Access controls",
        preview_steps=(
            "Read the current bucket Public Access Block configuration.",
            "Dry-run the four-control Public Access Block configuration.",
        ),
        verification_steps=(
            "Verify all four bucket Public Access Block controls are enabled.",
            "Re-run deterministic discovery and rule evaluation.",
        ),
        rollback_steps=(
            "Restore the exact pre-execution Public Access Block configuration.",
        ),
    ),
    RemediationAction(
        key="ec2.revoke_approved_public_ingress",
        version=1,
        rule_keys=frozenset(
            {
                "EC2_SG_SSH_OPEN_TO_WORLD",
                "EC2_SG_RDP_OPEN_TO_WORLD",
                "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD",
            }
        ),
        title="Remove the specifically approved public security-group ingress",
        preview_steps=(
            "Resolve the exact security-group rule from immutable finding evidence.",
            "Dry-run removal only when the current rule exactly matches the snapshot.",
        ),
        verification_steps=(
            "Verify the exact approved public ingress rule is absent.",
            "Re-run deterministic discovery and rule evaluation.",
        ),
        rollback_steps=(
            "Restore only the exact ingress rule captured in the immutable snapshot.",
        ),
    ),
    RemediationAction(
        key="s3.enable_default_encryption",  # gitleaks:allow
        version=1,
        rule_keys=frozenset({"S3_BUCKET_DEFAULT_ENCRYPTION_MISSING"}),
        title="Enable safe S3 default encryption",
        preview_steps=(
            "Read the current bucket encryption configuration.",
            "Dry-run enabling the organization-approved default encryption mode.",
        ),
        verification_steps=(
            "Verify default bucket encryption is enabled.",
            "Re-run deterministic discovery and rule evaluation.",
        ),
        rollback_steps=(
            "Restore the exact pre-execution bucket encryption configuration.",
        ),
    ),
)

default_remediation_actions = RemediationActionRegistry(DEFAULT_REMEDIATION_ACTIONS)
