# Teardown and cost control

> **Cost warning:** stopping EC2 does not eliminate EBS, S3, logging, snapshot, or other retained
> resource costs. Review the Terraform plan and cost inventory before apply and inspect the account
> after teardown.

## Before apply

- Confirm a dedicated non-production account and `ap-south-1`.
- Set a hard approved spending ceiling and expected duration.
- Review the saved plan hash and all cost-sensitive resources.
- Confirm termination protection and `prevent_destroy` behavior.

## Normal pause

Stopping the host pauses compute charges but retains the encrypted EBS volume and other resources.
Live-remediation flags must be disabled and emergency stop active before a pause.

## Destruction procedure

1. Preserve sanitized audit/test evidence outside source control.
2. Confirm no customer data and an empty synthetic bucket.
3. Verify Terraform state ownership, caller account, region, and mandatory sandbox tags.
4. Generate a destroy plan; confirm it is delete-only and allowlisted; record its hash.
5. Obtain the exact human destroy confirmation required by the repository wrapper.
6. Do not weaken bucket `prevent_destroy` until the empty bucket and final deletion are explicitly
   authorized.
7. Run the two-step wrapper, then verify EC2, EBS per policy, IAM roles, bucket, VPC resources, and
   any separately authorized Cloudflare route are gone.
8. Review billing for continuing resources.

No sandbox apply or teardown has been operationally performed in the current documented workflow.
