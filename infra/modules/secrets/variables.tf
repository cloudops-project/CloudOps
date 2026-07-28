variable "name" {
  type = string
}

variable "secret_names" {
  description = "Logical names for empty secret containers; values are populated out of band."
  type        = set(string)

  validation {
    condition = alltrue([
      for name in var.secret_names : can(regex("^[a-z0-9-]+$", name))
    ])
    error_message = "Secret logical names may contain only lowercase letters, digits, and hyphens."
  }
}

variable "recovery_window_in_days" {
  type    = number
  default = 30

  validation {
    condition     = var.recovery_window_in_days >= 7 && var.recovery_window_in_days <= 30
    error_message = "Secret recovery window must be between 7 and 30 days."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
