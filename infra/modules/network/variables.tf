variable "name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_cidr" {
  type = string

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be valid IPv4 CIDR notation."
  }
}

variable "availability_zones" {
  type = list(string)

  validation {
    condition     = length(var.availability_zones) >= 2
    error_message = "At least two availability zones are required."
  }
}

variable "single_nat_gateway" {
  description = "Cost-sensitive staging option. Production must set false."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
