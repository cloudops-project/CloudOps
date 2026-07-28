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

variable "ses_identity_arn" {
  type    = string
  default = ""
}

variable "certificate_arn" {
  type    = string
  default = ""
}

variable "alarm_email_endpoint" {
  type    = string
  default = ""
}
