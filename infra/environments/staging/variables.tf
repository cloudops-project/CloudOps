variable "aws_region" {
  type = string
}

variable "availability_zones" {
  type = list(string)
}

variable "api_image" {
  type = string
}

variable "web_image" {
  type = string
}

variable "allowed_origins" {
  type = list(string)

  validation {
    condition = (
      length(var.allowed_origins) > 0 &&
      alltrue([
        for origin in var.allowed_origins :
        can(regex(var.enable_http_only_staging ? "^http://" : "^https://", origin))
      ])
    )
    error_message = "allowed_origins must use HTTPS unless temporary HTTP-only staging is explicitly enabled."
  }
}

variable "customer_role_arns" {
  type    = set(string)
  default = []
}

variable "bedrock_model_arn" {
  type    = string
  default = ""
}

variable "bedrock_model_id" {
  type    = string
  default = ""
}

variable "ses_identity_arn" {
  type    = string
  default = ""
}

variable "certificate_arn" {
  type    = string
  default = ""

  validation {
    condition = (
      var.enable_http_only_staging ||
      can(regex("^arn:aws[a-z-]*:acm:", var.certificate_arn))
    )
    error_message = "Staging requires an ACM certificate ARN unless temporary HTTP-only staging is explicitly enabled."
  }
}

variable "frontend_url" {
  type = string

  validation {
    condition     = can(regex(var.enable_http_only_staging ? "^http://" : "^https://", var.frontend_url))
    error_message = "frontend_url must use HTTPS unless temporary HTTP-only staging is explicitly enabled."
  }
}

variable "trusted_hosts" {
  type = list(string)
}

variable "alarm_email_endpoint" {
  type    = string
  default = ""
}

variable "enable_http_only_staging" {
  description = "Temporary staging-only escape hatch for an unencrypted port-80 listener while DNS and ACM validation are pending."
  type        = bool
  default     = false

  validation {
    condition = (
      !var.enable_http_only_staging ||
      (
        var.bedrock_model_arn == "" &&
        var.bedrock_model_id == "" &&
        var.ses_identity_arn == ""
      )
    )
    error_message = "Temporary HTTP-only staging requires Bedrock and SES to remain disabled."
  }
}
