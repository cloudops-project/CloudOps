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
  type = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:acm:", var.certificate_arn))
    error_message = "Production-like staging requires an ACM certificate ARN."
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
