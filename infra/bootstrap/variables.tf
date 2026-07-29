variable "aws_region" {
  description = "AWS region for the Terraform state resources."
  type        = string
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for encrypted Terraform state."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket_name))
    error_message = "state_bucket_name must be a valid S3 bucket name."
  }
}

variable "lock_table_name" {
  description = "DynamoDB table used for Terraform state locking."
  type        = string
  default     = "cloudops-terraform-locks"
}

variable "tags" {
  description = "Non-sensitive tags applied to bootstrap resources."
  type        = map(string)
  default     = {}
}

variable "github_repository" {
  description = "Exact GitHub owner/repository allowed to request OIDC sessions."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must use owner/repository form."
  }
}

variable "deployment_environments" {
  description = "GitHub deployment-role environments to create. Staging is the safe default; production requires explicit enablement."
  type        = set(string)
  default     = ["staging"]

  validation {
    condition = (
      length(var.deployment_environments) > 0 &&
      alltrue([
        for environment in var.deployment_environments :
        contains(["staging", "production"], environment)
      ])
    )
    error_message = "deployment_environments must contain one or more supported values: staging or production."
  }
}

variable "github_oidc_provider_mode" {
  description = "How the GitHub Actions OIDC provider is resolved: create a new provider or reuse an explicitly supplied existing provider ARN."
  type        = string

  validation {
    condition     = contains(["create", "existing"], var.github_oidc_provider_mode)
    error_message = "github_oidc_provider_mode must be create or existing."
  }
}

variable "existing_github_oidc_provider_arn" {
  description = "Existing GitHub Actions OIDC provider ARN. Required only when github_oidc_provider_mode is existing."
  type        = string
  default     = ""

  validation {
    condition = (
      (var.github_oidc_provider_mode == "create" && var.existing_github_oidc_provider_arn == "") ||
      (
        var.github_oidc_provider_mode == "existing" &&
        can(regex(
          "^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$",
          var.existing_github_oidc_provider_arn
        ))
      )
    )
    error_message = "Create mode requires an empty existing provider ARN; existing mode requires the exact GitHub Actions OIDC provider ARN."
  }
}
