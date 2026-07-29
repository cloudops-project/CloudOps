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
  aws_region         = "us-east-1"
  availability_zones = ["us-east-1a", "us-east-1b"]
  api_image          = "000000000000.dkr.ecr.us-east-1.amazonaws.com/cloudops-staging-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  web_image          = "000000000000.dkr.ecr.us-east-1.amazonaws.com/cloudops-staging-web@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  allowed_origins    = ["https://staging.example.invalid"]
  certificate_arn    = "arn:aws:acm:us-east-1:000000000000:certificate/00000000-0000-0000-0000-000000000000"
  frontend_url       = "https://staging.example.invalid"
  trusted_hosts      = ["staging.example.invalid"]
}

run "https_is_the_default" {
  command = plan

  assert {
    condition     = output.public_protocol == "https"
    error_message = "Staging must use HTTPS by default."
  }

  assert {
    condition     = output.public_listener_ports == [443]
    error_message = "Default staging must expose only the HTTPS listener."
  }

  assert {
    condition     = output.temporary_http_staging_warning == ""
    error_message = "Secure staging must not emit the temporary HTTP warning."
  }
}

run "normal_staging_requires_certificate" {
  command = plan

  variables {
    certificate_arn = ""
  }

  expect_failures = [var.certificate_arn]
}

run "temporary_http_accepts_empty_certificate" {
  command = plan

  variables {
    enable_http_only_staging = true
    certificate_arn          = ""
    frontend_url             = "http://temporary-staging.example.invalid"
    allowed_origins          = ["http://temporary-staging.example.invalid"]
  }

  assert {
    condition     = output.public_protocol == "http"
    error_message = "Temporary HTTP staging must report HTTP as the active protocol."
  }

  assert {
    condition     = output.public_listener_ports == [80]
    error_message = "Temporary HTTP staging must expose only port 80."
  }

  assert {
    condition     = output.temporary_http_staging_warning != ""
    error_message = "Temporary HTTP staging must emit an explicit warning."
  }
}

run "http_urls_require_explicit_http_mode" {
  command = plan

  variables {
    frontend_url    = "http://temporary-staging.example.invalid"
    allowed_origins = ["http://temporary-staging.example.invalid"]
  }

  expect_failures = [
    var.frontend_url,
    var.allowed_origins,
  ]
}

run "temporary_http_rejects_live_providers" {
  command = plan

  variables {
    enable_http_only_staging = true
    certificate_arn          = ""
    frontend_url             = "http://temporary-staging.example.invalid"
    allowed_origins          = ["http://temporary-staging.example.invalid"]
    bedrock_model_arn        = "arn:aws:bedrock:us-east-1::foundation-model/synthetic"
    bedrock_model_id         = "synthetic"
  }

  expect_failures = [var.enable_http_only_staging]
}
