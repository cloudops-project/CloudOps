variable "expected_aws_account_id" {
  description = "Exact non-root sandbox account ID approved by the operator."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_aws_account_id))
    error_message = "expected_aws_account_id must be exactly 12 digits."
  }
}

variable "aws_region" {
  description = "Approved sandbox region."
  type        = string
  default     = "ap-south-1"

  validation {
    condition     = var.aws_region == "ap-south-1"
    error_message = "The governed V1 sandbox is restricted to ap-south-1."
  }
}

variable "administrator_cidr" {
  description = "Single explicitly approved administrator IPv4 CIDR for SSH."
  type        = string

  validation {
    condition = (
      can(cidrhost(var.administrator_cidr, 0)) &&
      var.administrator_cidr != "0.0.0.0/0"
    )
    error_message = "administrator_cidr must be a valid, non-global IPv4 CIDR."
  }
}

variable "hosting_instance_type" {
  description = "CloudOps self-host instance type."
  type        = string
  default     = "t3a.large"
}

variable "hosting_key_name" {
  description = "Optional existing EC2 key pair. Prefer Session Manager when possible."
  type        = string
  default     = null
  nullable    = true
}

variable "enable_termination_protection" {
  description = "Protect the hosting instance from API termination."
  type        = bool
  default     = true
}

variable "discovery_external_id" {
  description = "Separate trust material for the read-only discovery role."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.discovery_external_id) >= 24 && length(var.discovery_external_id) <= 256
    error_message = "discovery_external_id must contain 24 to 256 characters."
  }
}

variable "remediation_external_id" {
  description = "Separate trust material for the narrowly scoped remediation role."
  type        = string
  sensitive   = true

  validation {
    condition = (
      length(var.remediation_external_id) >= 24 &&
      length(var.remediation_external_id) <= 256 &&
      var.remediation_external_id != var.discovery_external_id
    )
    error_message = "remediation_external_id must be distinct and contain 24 to 256 characters."
  }
}

variable "lab_bucket_name" {
  description = "Globally unique empty test bucket name owned by this Terraform state."
  type        = string

  validation {
    condition     = can(regex("^cloudops-lab-[a-z0-9][a-z0-9.-]{2,50}[a-z0-9]$", var.lab_bucket_name))
    error_message = "lab_bucket_name must be a valid cloudops-lab-* bucket name."
  }
}

variable "enable_optional_test_instance" {
  description = "Create a private, non-public test instance. Disabled by default."
  type        = bool
  default     = false
}

variable "state_owner" {
  description = "Non-secret identifier for the team that owns the Terraform state."
  type        = string
  default     = "cloudops-platform"
}
