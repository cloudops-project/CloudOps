mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "000000000000"
    }
  }

  mock_data "aws_partition" {
    defaults = {
      partition = "aws"
    }
  }

  mock_data "aws_iam_policy_document" {
    defaults = {
      json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}"
    }
  }

  mock_resource "aws_kms_key" {
    defaults = {
      arn    = "arn:aws:kms:us-east-1:000000000000:key/00000000-0000-0000-0000-000000000000"
      key_id = "00000000-0000-0000-0000-000000000000"
    }
  }
}

variables {
  aws_region                = "us-east-1"
  state_bucket_name         = "cloudops-bootstrap-test-state"
  github_repository         = "cloudops-project/CloudOps"
  github_oidc_provider_mode = "create"
}

run "default_is_staging_only" {
  command = plan

  assert {
    condition     = keys(aws_iam_role.github_deploy) == ["staging"]
    error_message = "The default bootstrap must create only the staging deployment role."
  }

  assert {
    condition     = keys(aws_iam_role_policy.github_deploy) == ["staging"]
    error_message = "The default bootstrap must attach a deployment policy only to staging."
  }
}

run "production_requires_explicit_enablement" {
  command = plan

  variables {
    deployment_environments = ["staging", "production"]
  }

  assert {
    condition = (
      length(aws_iam_role.github_deploy) == 2 &&
      contains(keys(aws_iam_role.github_deploy), "staging") &&
      contains(keys(aws_iam_role.github_deploy), "production")
    )
    error_message = "Production must appear only when it is explicitly selected."
  }
}

run "unsupported_environment_is_rejected" {
  command = plan

  variables {
    deployment_environments = ["development"]
  }

  expect_failures = [var.deployment_environments]
}

run "empty_environment_set_is_rejected" {
  command = plan

  variables {
    deployment_environments = []
  }

  expect_failures = [var.deployment_environments]
}

run "create_mode_resolves_created_provider" {
  command = plan

  override_resource {
    target = aws_iam_openid_connect_provider.github[0]
    values = {
      arn = "arn:aws:iam::000000000000:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 1
    error_message = "Create mode must manage exactly one GitHub OIDC provider."
  }

  assert {
    condition     = output.github_oidc_provider_created
    error_message = "Create mode must report that the provider is managed."
  }
}

run "existing_mode_resolves_supplied_provider" {
  command = plan

  variables {
    github_oidc_provider_mode         = "existing"
    existing_github_oidc_provider_arn = "arn:aws:iam::000000000000:oidc-provider/token.actions.githubusercontent.com"
  }

  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "Existing mode must not create an OIDC provider."
  }

  assert {
    condition     = output.github_oidc_provider_arn == var.existing_github_oidc_provider_arn
    error_message = "Existing mode must resolve the explicitly supplied provider ARN."
  }

  assert {
    condition     = !output.github_oidc_provider_created
    error_message = "Existing mode must report that the provider is not managed."
  }
}

run "unsupported_oidc_mode_is_rejected" {
  command = plan

  variables {
    github_oidc_provider_mode = "discover"
  }

  expect_failures = [var.github_oidc_provider_mode]
}

run "existing_mode_requires_provider_arn" {
  command = plan

  variables {
    github_oidc_provider_mode = "existing"
  }

  expect_failures = [var.existing_github_oidc_provider_arn]
}

run "existing_mode_rejects_malformed_provider_arn" {
  command = plan

  variables {
    github_oidc_provider_mode         = "existing"
    existing_github_oidc_provider_arn = "not-an-oidc-provider-arn"
  }

  expect_failures = [var.existing_github_oidc_provider_arn]
}

run "create_mode_rejects_conflicting_provider_arn" {
  command = plan

  variables {
    github_oidc_provider_mode         = "create"
    existing_github_oidc_provider_arn = "arn:aws:iam::000000000000:oidc-provider/token.actions.githubusercontent.com"
  }

  expect_failures = [var.existing_github_oidc_provider_arn]
}
