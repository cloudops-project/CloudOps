mock_provider "aws" {}

override_data {
  target = data.aws_ssm_parameter.ubuntu_2404_amd64
  values = { value = "ami-00000000000000000" }
}

override_data {
  target = data.aws_partition.current
  values = { partition = "aws" }
}

override_data {
  target = data.aws_iam_policy_document.ec2_trust
  values = { json = "{}" }
}

override_data {
  target = data.aws_iam_policy_document.sandbox_role_trust
  values = { json = "{}" }
}

override_data {
  target = data.aws_iam_policy_document.remediation_role_trust
  values = { json = "{}" }
}

override_data {
  target = data.aws_iam_policy_document.discovery_additional
  values = { json = "{}" }
}

override_data {
  target = data.aws_iam_policy_document.platform_assume_roles
  values = { json = "{}" }
}

override_data {
  target = data.aws_iam_policy_document.remediation
  values = { json = "{}" }
}

override_data {
  target = data.aws_iam_policy_document.platform_ses
  values = { json = "{}" }
}

variables {
  expected_aws_account_id = "111122223333"
  administrator_cidr      = "192.0.2.10/32"
  discovery_external_id   = "synthetic-discovery-external-id"
  remediation_external_id = "synthetic-remediation-external-id"
  lab_bucket_name         = "cloudops-lab-synthetic-example"
}

run "safe_defaults" {
  command = plan

  assert {
    condition     = aws_vpc.sandbox.cidr_block == "10.50.0.0/16"
    error_message = "The sandbox VPC boundary changed."
  }

  assert {
    condition     = length(aws_instance.optional_test) == 0
    error_message = "The optional test instance must be disabled by default."
  }

  assert {
    condition     = aws_instance.hosting.metadata_options[0].http_tokens == "required"
    error_message = "The hosting instance must require IMDSv2."
  }

  assert {
    condition     = aws_s3_account_public_access_block.sandbox.block_public_acls
    error_message = "Account-level S3 Public Access Block must remain enabled."
  }

  assert {
    condition     = !aws_s3_bucket_public_access_block.intentional_test.restrict_public_buckets
    error_message = "The bucket-level test finding must remain intentionally detectable."
  }
}
