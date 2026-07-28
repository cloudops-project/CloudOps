variable "aws_region" {
  type = string
}

variable "availability_zones" {
  type = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "Production requires at least two availability zones."
  }
}

variable "api_image" {
  type = string
}

variable "web_image" {
  type = string
}

variable "allowed_origins" {
  type = list(string)
}

variable "customer_role_arns" {
  type = set(string)
}

variable "bedrock_model_arn" {
  type = string
}

variable "bedrock_model_id" {
  type = string
}

variable "ses_identity_arn" {
  type = string
}

variable "certificate_arn" {
  type = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:acm:", var.certificate_arn))
    error_message = "Production requires an ACM certificate ARN."
  }
}

variable "frontend_url" {
  type = string
}

variable "trusted_hosts" {
  type = list(string)
}

variable "alarm_email_endpoint" {
  type    = string
  default = ""
}
