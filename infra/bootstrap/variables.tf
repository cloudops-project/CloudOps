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
