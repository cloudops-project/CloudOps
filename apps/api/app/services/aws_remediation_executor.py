from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]

from app.core.config import Settings
from app.models.enums import AssetType
from app.services.aws_credentials import (
    AWSConnectionFailure,
    RemediationRoleCredentialProvider,
)
from app.services.remediation_executor import (
    RemediationExecutionContext,
    RemediationExecutionOutcome,
    RemediationExecutionResult,
)

S3_PUBLIC_ACCESS_BLOCK_KEYS = (
    "BlockPublicAcls",
    "IgnorePublicAcls",
    "BlockPublicPolicy",
    "RestrictPublicBuckets",
)
REQUIRED_REMEDIATION_TAGS = {
    "CloudOpsLab": "true",
    "Environment": "cloudops-test",
    "AllowCloudOpsRemediation": "true",
}
SECURITY_GROUP_RULE_FIELDS = (
    "GroupId",
    "SecurityGroupRuleId",
    "IsEgress",
    "IpProtocol",
    "FromPort",
    "ToPort",
    "CidrIpv4",
    "CidrIpv6",
    "PrefixListId",
    "ReferencedGroupInfo",
    "Description",
)


class _Refusal(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AWSRemediationExecutor:
    """Static, fail-closed executor for the two approved sandbox actions."""

    key = "aws"

    def __init__(
        self,
        settings: Settings,
        *,
        client_factory: Callable[[str, str | None], Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    def execute(
        self,
        *,
        action_key: str,
        finding_id: uuid.UUID,
        snapshot_hash: str,
        dry_run: bool,
        context: RemediationExecutionContext | None = None,
    ) -> RemediationExecutionResult:
        del finding_id, snapshot_hash
        try:
            if context is None:
                raise _Refusal("execution_context_missing")
            if dry_run:
                raise _Refusal("live_execution_requires_non_dry_run_request")
            client_factory = self.client_factory or RemediationRoleCredentialProvider(
                context.account, self.settings
            ).client
            dispatch = {
                "s3.enable_public_access_block": self._s3_public_access_block,
                "ec2.revoke_approved_public_ingress": self._ec2_revoke_ingress,
            }
            handler = dispatch.get(action_key)
            if handler is None:
                raise _Refusal("action_not_allowed")
            return handler(context, client_factory)
        except _Refusal as exc:
            return self._failure(exc.code)
        except AWSConnectionFailure as exc:
            return self._failure(exc.reason)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "client_error"))
            safe = re.sub(r"[^a-z0-9]+", "_", code.casefold()).strip("_")
            return self._failure(f"aws_{safe or 'client_error'}")
        except (BotoCoreError, KeyError, TypeError, ValueError):
            return self._failure("aws_remediation_failed")

    @staticmethod
    def _failure(code: str) -> RemediationExecutionResult:
        return RemediationExecutionResult(
            outcome=RemediationExecutionOutcome.FAILURE,
            before_state={"captured": False},
            sanitized_error=code,
        )

    def _s3_public_access_block(
        self,
        context: RemediationExecutionContext,
        client_factory: Callable[[str, str | None], Any],
    ) -> RemediationExecutionResult:
        asset = context.asset
        if asset.asset_type != AssetType.S3_BUCKET:
            raise _Refusal("target_type_mismatch")
        bucket = asset.resource_id
        if not bucket.startswith("cloudops-lab-"):
            raise _Refusal("s3_bucket_prefix_not_allowed")
        client = client_factory("s3", asset.region)
        tags_response = client.get_bucket_tagging(Bucket=bucket)
        tags = {
            str(item.get("Key")): str(item.get("Value"))
            for item in tags_response.get("TagSet", [])
            if item.get("Key") is not None
        }
        self._require_tags(tags)
        before_response_id: str | None = None
        try:
            before_response = client.get_public_access_block(Bucket=bucket)
            before_response_id = self._request_id(before_response)
            before = self._normalize_public_access_block(
                before_response.get("PublicAccessBlockConfiguration")
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != (
                "NoSuchPublicAccessBlockConfiguration"
            ):
                raise
            before = None
        approved = asset.metadata_json.get("public_access_block")
        if before != approved:
            raise _Refusal("remediation_precondition_drift")
        desired = {key: True for key in S3_PUBLIC_ACCESS_BLOCK_KEYS}
        write_response = client.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration=desired,
        )
        verified_response = client.get_public_access_block(Bucket=bucket)
        verified = self._normalize_public_access_block(
            verified_response.get("PublicAccessBlockConfiguration")
        )
        if verified != desired:
            raise _Refusal("remediation_verification_failed")
        request_ids = self._request_ids(
            read_before=before_response_id,
            mutate=self._request_id(write_response),
            verify=self._request_id(verified_response),
        )
        return RemediationExecutionResult(
            outcome=RemediationExecutionOutcome.SUCCESS,
            before_state={"public_access_block": before},
            after_state={"public_access_block": verified},
            precondition_evidence={"matched": True, "tags_verified": True},
            verification_result={"matched": True},
            rollback_state={
                "public_access_block": before,
                "configuration_was_absent": before is None,
            },
            aws_request_ids=request_ids,
        )

    def _ec2_revoke_ingress(
        self,
        context: RemediationExecutionContext,
        client_factory: Callable[[str, str | None], Any],
    ) -> RemediationExecutionResult:
        asset = context.asset
        if asset.asset_type != AssetType.EC2_SECURITY_GROUP:
            raise _Refusal("target_type_mismatch")
        group_id = asset.resource_id
        client = client_factory("ec2", asset.region)
        group_response = client.describe_security_groups(GroupIds=[group_id])
        groups = group_response.get("SecurityGroups", [])
        if len(groups) != 1:
            raise _Refusal("security_group_not_found")
        group = groups[0]
        if group.get("GroupId") != group_id:
            raise _Refusal("target_resource_mismatch")
        if group.get("VpcId") != asset.metadata_json.get("vpc_id"):
            raise _Refusal("remediation_precondition_drift")
        self._require_tags(self._ec2_tags(group.get("Tags", [])))
        approved = self._approved_rule(context)
        before_rules = self._security_group_rules(client, group_id)
        current = next(
            (
                rule
                for rule in before_rules
                if rule.get("SecurityGroupRuleId")
                == approved.get("SecurityGroupRuleId")
            ),
            None,
        )
        if current != approved:
            raise _Refusal("remediation_precondition_drift")
        response = client.revoke_security_group_ingress(
            GroupId=group_id,
            SecurityGroupRuleIds=[str(approved["SecurityGroupRuleId"])],
        )
        after_rules = self._security_group_rules(client, group_id)
        if any(
            rule.get("SecurityGroupRuleId") == approved.get("SecurityGroupRuleId")
            for rule in after_rules
        ):
            raise _Refusal("remediation_verification_failed")
        unrelated_before = {
            str(rule.get("SecurityGroupRuleId")): rule
            for rule in before_rules
            if rule.get("SecurityGroupRuleId") != approved.get("SecurityGroupRuleId")
        }
        unrelated_after = {
            str(rule.get("SecurityGroupRuleId")): rule for rule in after_rules
        }
        if unrelated_before != unrelated_after:
            raise _Refusal("unrelated_security_group_rule_changed")
        return RemediationExecutionResult(
            outcome=RemediationExecutionOutcome.SUCCESS,
            before_state={"security_group_rule": approved},
            after_state={"security_group_rule_present": False},
            precondition_evidence={"matched": True, "tags_verified": True},
            verification_result={"matched": True, "unrelated_rules_unchanged": True},
            rollback_state={"security_group_rule": approved},
            aws_request_ids=self._request_ids(
                describe_group=self._request_id(group_response),
                mutate=self._request_id(response),
            ),
        )

    def _approved_rule(self, context: RemediationExecutionContext) -> dict[str, object]:
        raw_rules = context.asset.metadata_json.get("security_group_rules")
        if not isinstance(raw_rules, list):
            raise _Refusal("security_group_rule_evidence_missing")
        candidates = [
            self._normalize_rule(rule)
            for rule in raw_rules
            if isinstance(rule, dict)
            and rule.get("GroupId") == context.asset.resource_id
            and rule.get("IsEgress") is False
            and self._matches_finding(context.finding.rule_key, rule)
        ]
        if len(candidates) != 1 or not candidates[0].get("SecurityGroupRuleId"):
            raise _Refusal("security_group_rule_not_unambiguous")
        return candidates[0]

    @staticmethod
    def _matches_finding(rule_key: str, rule: dict[str, Any]) -> bool:
        world = rule.get("CidrIpv4") == "0.0.0.0/0" or rule.get("CidrIpv6") == "::/0"
        if not world:
            return False
        protocol = str(rule.get("IpProtocol"))
        start = rule.get("FromPort")
        end = rule.get("ToPort")
        if rule_key == "EC2_SG_ALL_TRAFFIC_OPEN_TO_WORLD":
            return protocol == "-1"
        port = 22 if rule_key == "EC2_SG_SSH_OPEN_TO_WORLD" else 3389
        return protocol == "tcp" and start == port and end == port

    def _security_group_rules(self, client: Any, group_id: str) -> list[dict[str, object]]:
        rules: list[dict[str, object]] = []
        paginator = client.get_paginator("describe_security_group_rules")
        for page in paginator.paginate(Filters=[{"Name": "group-id", "Values": [group_id]}]):
            for item in page.get("SecurityGroupRules", []):
                if isinstance(item, dict) and item.get("GroupId") == group_id:
                    rules.append(self._normalize_rule(item))
        return sorted(rules, key=lambda item: str(item.get("SecurityGroupRuleId", "")))

    @staticmethod
    def _normalize_rule(rule: dict[str, Any]) -> dict[str, object]:
        return {
            field: (rule[field] is True if field == "IsEgress" else rule[field])
            for field in SECURITY_GROUP_RULE_FIELDS
            if field in rule
        }

    @staticmethod
    def _normalize_public_access_block(value: object) -> dict[str, bool] | None:
        if not isinstance(value, dict):
            return None
        return {key: value[key] is True for key in S3_PUBLIC_ACCESS_BLOCK_KEYS if key in value}

    @staticmethod
    def _ec2_tags(items: object) -> dict[str, str]:
        if not isinstance(items, list):
            return {}
        return {
            str(item.get("Key")): str(item.get("Value"))
            for item in items
            if isinstance(item, dict) and item.get("Key") is not None
        }

    @staticmethod
    def _require_tags(tags: dict[str, str]) -> None:
        if any(tags.get(key) != value for key, value in REQUIRED_REMEDIATION_TAGS.items()):
            raise _Refusal("required_remediation_tags_missing")

    @staticmethod
    def _request_id(response: object) -> str | None:
        if not isinstance(response, dict):
            return None
        metadata = response.get("ResponseMetadata")
        if not isinstance(metadata, dict):
            return None
        value = metadata.get("RequestId")
        return str(value)[:128] if value else None

    @staticmethod
    def _request_ids(**values: str | None) -> dict[str, object] | None:
        bounded: dict[str, object] = {
            key: value for key, value in values.items() if value
        }
        return bounded or None
