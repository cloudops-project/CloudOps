variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "application_security_group_id" {
  type = string
}

variable "instance_class" {
  type = string
}

variable "allocated_storage_gib" {
  type = number

  validation {
    condition     = var.allocated_storage_gib >= 20
    error_message = "RDS storage must be at least 20 GiB."
  }
}

variable "max_allocated_storage_gib" {
  type = number
}

variable "multi_az" {
  type = bool
}

variable "deletion_protection" {
  type = bool
}

variable "skip_final_snapshot" {
  type = bool
}

variable "backup_retention_days" {
  type = number

  validation {
    condition     = var.backup_retention_days >= 7 && var.backup_retention_days <= 35
    error_message = "RDS backups must be retained between 7 and 35 days."
  }
}

variable "alarm_topic_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
