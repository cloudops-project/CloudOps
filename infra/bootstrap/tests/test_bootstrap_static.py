"""Static regression checks for the credential-free Terraform bootstrap contract."""

from pathlib import Path
import unittest


BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
MAIN_TF = (BOOTSTRAP_ROOT / "main.tf").read_text(encoding="utf-8")
VARIABLES_TF = (BOOTSTRAP_ROOT / "variables.tf").read_text(encoding="utf-8")
STATE_KMS_POLICY = MAIN_TF.split(
    'data "aws_iam_policy_document" "state_kms"',
    maxsplit=1,
)[1].split('resource "aws_kms_key" "state"', maxsplit=1)[0]


class BootstrapStaticTests(unittest.TestCase):
    def test_state_key_policy_authorizes_automatic_rotation(self) -> None:
        self.assertIn('"kms:EnableKeyRotation"', STATE_KMS_POLICY)
        self.assertNotIn('"kms:*"', STATE_KMS_POLICY)

    def test_environment_role_creation_uses_validated_input(self) -> None:
        self.assertIn('default     = ["staging"]', VARIABLES_TF)
        self.assertIn('contains(["staging", "production"], environment)', VARIABLES_TF)
        self.assertGreaterEqual(
            MAIN_TF.count("for_each = var.deployment_environments"),
            2,
        )
        self.assertNotIn('toset(["staging", "production"])', MAIN_TF)

    def test_oidc_provider_is_explicit_and_trust_uses_resolved_arn(self) -> None:
        self.assertIn(
            'count = var.github_oidc_provider_mode == "create" ? 1 : 0',
            MAIN_TF,
        )
        self.assertIn(
            "? one(aws_iam_openid_connect_provider.github[*].arn)",
            MAIN_TF,
        )
        self.assertIn(
            ": var.existing_github_oidc_provider_arn",
            MAIN_TF,
        )
        self.assertEqual(
            MAIN_TF.count("identifiers = [local.github_oidc_provider_arn]"),
            2,
        )
        self.assertIn(
            'values   = ["repo:${var.github_repository}:ref:refs/heads/main"]',
            MAIN_TF,
        )
        self.assertIn(
            'values   = ["repo:${var.github_repository}:environment:${each.key}"]',
            MAIN_TF,
        )
        self.assertIn('values   = ["sts.amazonaws.com"]', MAIN_TF)

    def test_existing_deployment_permissions_remain_restricted(self) -> None:
        expected_permissions = {
            '"ecs:RegisterTaskDefinition"',
            '"ecs:UpdateService"',
            '"ecs:RunTask"',
            '"ecs:StopTask"',
            '"iam:PassRole"',
            '"cloudwatch:DescribeAlarms"',
            '"logs:GetLogEvents"',
            '"logs:StartQuery"',
            '"logs:GetQueryResults"',
        }
        for permission in expected_permissions:
            with self.subTest(permission=permission):
                self.assertIn(permission, MAIN_TF)

        self.assertIn("repository/cloudops-*", MAIN_TF)
        self.assertIn("service/cloudops-*/*", MAIN_TF)
        self.assertIn("role/cloudops-*", MAIN_TF)
        self.assertIn('values   = ["ecs-tasks.amazonaws.com"]', MAIN_TF)
        self.assertNotIn('"iam:*"', MAIN_TF)
        self.assertNotIn('"ecs:*"', MAIN_TF)
        self.assertNotIn('"ecr:*"', MAIN_TF)


if __name__ == "__main__":
    unittest.main()
