"""Static security contract for the temporary staging HTTP escape hatch."""

from pathlib import Path
import unittest


INFRA_ROOT = Path(__file__).resolve().parents[1]
STAGING_VARIABLES = (INFRA_ROOT / "environments/staging/variables.tf").read_text(
    encoding="utf-8"
)
STAGING_MAIN = (INFRA_ROOT / "environments/staging/main.tf").read_text(encoding="utf-8")
STAGING_OUTPUTS = (INFRA_ROOT / "environments/staging/outputs.tf").read_text(
    encoding="utf-8"
)
PRODUCTION_VARIABLES = (INFRA_ROOT / "environments/production/variables.tf").read_text(
    encoding="utf-8"
)
PRODUCTION_MAIN = (INFRA_ROOT / "environments/production/main.tf").read_text(
    encoding="utf-8"
)
PLATFORM_VARIABLES = (INFRA_ROOT / "modules/platform/variables.tf").read_text(
    encoding="utf-8"
)
PLATFORM_MAIN = (INFRA_ROOT / "modules/platform/main.tf").read_text(encoding="utf-8")
PLATFORM_OUTPUTS = (INFRA_ROOT / "modules/platform/outputs.tf").read_text(
    encoding="utf-8"
)
DATABASE_MAIN = (INFRA_ROOT / "modules/database/main.tf").read_text(encoding="utf-8")


class TemporaryHttpStagingTests(unittest.TestCase):
    def test_escape_hatch_defaults_off_and_is_staging_only(self) -> None:
        self.assertIn('variable "enable_http_only_staging"', STAGING_VARIABLES)
        self.assertIn("default     = false", STAGING_VARIABLES)
        self.assertIn('var.environment == "staging"', PLATFORM_VARIABLES)
        self.assertNotIn("enable_http_only_staging", PRODUCTION_VARIABLES)
        self.assertNotIn("enable_http_only_staging", PRODUCTION_MAIN)

    def test_certificate_and_urls_are_mode_gated(self) -> None:
        self.assertIn(
            "var.enable_http_only_staging ||",
            STAGING_VARIABLES,
        )
        self.assertIn(
            'var.enable_http_only_staging ? "^http://" : "^https://"',
            STAGING_VARIABLES,
        )
        self.assertIn(
            'var.enable_http_only_staging ? "^http://" : "^https://"',
            PLATFORM_VARIABLES,
        )

    def test_listener_selection_is_mutually_exclusive(self) -> None:
        self.assertIn(
            'resource "aws_lb_listener" "https"',
            PLATFORM_MAIN,
        )
        self.assertIn(
            'resource "aws_lb_listener" "temporary_staging_http"',
            PLATFORM_MAIN,
        )
        self.assertGreaterEqual(
            PLATFORM_MAIN.count(
                "count = var.enable_http_only_staging ? 0 : 1",
            ),
            2,
        )
        self.assertGreaterEqual(
            PLATFORM_MAIN.count(
                "count = var.enable_http_only_staging ? 1 : 0",
            ),
            2,
        )

    def test_active_protocol_and_warning_are_outputs(self) -> None:
        self.assertIn('output "public_protocol"', PLATFORM_OUTPUTS)
        self.assertIn('output "public_listener_ports"', PLATFORM_OUTPUTS)
        self.assertIn('output "temporary_http_staging_warning"', PLATFORM_OUTPUTS)
        self.assertIn('output "public_protocol"', STAGING_OUTPUTS)
        self.assertIn("traffic is unencrypted", PLATFORM_OUTPUTS)
        self.assertIn('TemporaryHttpStaging = "true"', STAGING_MAIN)

    def test_private_network_and_waf_boundaries_remain(self) -> None:
        self.assertEqual(PLATFORM_MAIN.count("assign_public_ip = false"), 4)
        self.assertIn(
            "referenced_security_group_id = aws_security_group.application.id",
            PLATFORM_MAIN,
        )
        self.assertIn(
            "referenced_security_group_id = aws_security_group.load_balancer.id",
            PLATFORM_MAIN,
        )
        self.assertIn(
            'resource "aws_wafv2_web_acl_association" "this"',
            PLATFORM_MAIN,
        )
        self.assertIn("publicly_accessible    = false", DATABASE_MAIN)
        self.assertIn("storage_encrypted     = true", DATABASE_MAIN)

    def test_http_checkov_exceptions_are_resource_specific(self) -> None:
        resource_start = PLATFORM_MAIN.index(
            'resource "aws_lb_listener" "temporary_staging_http"'
        )
        listener_start = PLATFORM_MAIN.rindex("# checkov:skip=", 0, resource_start)
        listener_end = PLATFORM_MAIN.index(
            'resource "aws_lb_listener_rule" "api_temporary_staging_http"'
        )
        listener = PLATFORM_MAIN[listener_start:listener_end]
        self.assertIn("checkov:skip=CKV_AWS_2:", listener)
        self.assertIn("checkov:skip=CKV_AWS_103:", listener)

        load_balancer_start = PLATFORM_MAIN.rindex(
            "# checkov:skip=",
            0,
            PLATFORM_MAIN.index('resource "aws_lb" "this"'),
        )
        load_balancer_end = PLATFORM_MAIN.index('resource "aws_lb_target_group" "api"')
        load_balancer = PLATFORM_MAIN[load_balancer_start:load_balancer_end]
        self.assertIn("checkov:skip=CKV2_AWS_20:", load_balancer)
        self.assertEqual(PLATFORM_MAIN.count("checkov:skip=CKV2_AWS_20:"), 1)


if __name__ == "__main__":
    unittest.main()
