export type Role =
  | "owner"
  | "admin"
  | "security_analyst"
  | "cloud_engineer"
  | "auditor"
  | "viewer";
export type MembershipStatus = "active" | "suspended" | "removed";
export interface User {
  id: string;
  email: string;
  full_name: string;
  status: string;
}
export interface Organization {
  id: string;
  name: string;
  slug: string;
  role: Role;
}
export interface Me {
  user: User;
  organizations: Organization[];
}
export interface Member {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  status: MembershipStatus;
}
export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: string;
  development_token?: string;
}
export interface AuditEvent {
  id: string;
  event_type: string;
  result: string;
  created_at: string;
}
export type AWSAccountStatus =
  "pending" | "connected" | "failed" | "disconnected";
export interface AWSAccount {
  id: string;
  organization_id: string;
  name: string;
  account_id: string;
  role_arn: string | null;
  external_id: string;
  status: AWSAccountStatus;
  connection_status: AWSAccountStatus;
  failure_reason: string | null;
  last_validated_at: string | null;
}
export interface AWSAccountDetail {
  account: AWSAccount;
  trust_policy: Record<string, unknown>;
  permission_policy: {
    policy_name: string;
    managed_policy_arn: string;
    description: string;
  };
  onboarding_instructions: string[];
}
export type AssetType =
  | "ec2_instance"
  | "ec2_security_group"
  | "ebs_volume"
  | "s3_bucket"
  | "iam_user"
  | "iam_role"
  | "iam_group"
  | "iam_policy"
  | "rds_instance"
  | "cloudwatch_alarm"
  | "cloudwatch_log_group"
  | "cloudtrail_trail";
export interface Asset {
  id: string;
  organization_id: string;
  aws_account_id: string;
  asset_type: AssetType;
  resource_id: string;
  arn: string | null;
  name: string;
  region: string;
  status: string | null;
  tags: Record<string, string>;
  metadata: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
  is_active: boolean;
}
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export type DiscoveryStatus =
  "pending" | "running" | "completed" | "partially_completed" | "failed";
export interface DiscoveryJob {
  id: string;
  organization_id: string;
  aws_account_id: string;
  status: DiscoveryStatus;
  started_at: string | null;
  finished_at: string | null;
  assets_discovered: number;
  assets_created: number;
  assets_updated: number;
  assets_deactivated: number;
  error_summary: string | null;
}

export type FindingSeverity =
  "critical" | "high" | "medium" | "low" | "informational";
export type FindingStatus = "open" | "resolved" | "suppressed";
export interface SecurityRule {
  key: string;
  version: number;
  name: string;
  description: string;
  service: string;
  asset_type: AssetType | null;
  asset_types: AssetType[];
  category: string;
  severity: FindingSeverity;
  remediation: string;
  references: string[];
  enabled_by_default: boolean;
}
export interface Finding {
  id: string;
  organization_id: string;
  aws_account_id: string;
  asset_id: string | null;
  rule_key: string;
  rule_version: number;
  severity: FindingSeverity;
  category: string;
  service: string;
  asset_type: AssetType | null;
  region: string | null;
  remediation: string;
  references: string[];
  status: FindingStatus;
  evidence: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  suppressed_at: string | null;
  suppressed_until: string | null;
  suppression_reason: string | null;
  last_evaluation_id: string;
}
export type EvaluationStatus =
  "pending" | "running" | "completed" | "partially_completed" | "failed";
export interface EvaluationJob {
  id: string;
  organization_id: string;
  aws_account_id: string;
  sequence: number;
  status: EvaluationStatus;
  assets_evaluated: number;
  rules_evaluated: number;
  passed_count: number;
  failed_count: number;
  error_count: number;
  not_applicable_count: number;
  findings_created: number;
  findings_updated: number;
  findings_resolved: number;
  findings_reopened: number;
  evaluation_errors: number;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
}
export interface FindingSummary {
  total: number;
  items: Array<{
    severity: FindingSeverity;
    status: FindingStatus;
    service: string;
    aws_account_id: string;
    asset_type: AssetType | null;
    region: string | null;
    count: number;
  }>;
}
