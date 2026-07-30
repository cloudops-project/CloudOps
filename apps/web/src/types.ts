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
export type AuditResult = "succeeded" | "failed" | "denied";
export interface AuditEvent {
  id: string;
  organization_id: string | null;
  actor_user_id: string | null;
  event_type: string;
  resource_type: string;
  resource_id: string | null;
  result: AuditResult | string;
  metadata_json?: Record<string, unknown>;
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
  status: AWSAccountStatus;
  connection_status: AWSAccountStatus;
  failure_reason: string | null;
  last_validated_at: string | null;
}
export interface AWSAccountDetail {
  account: AWSAccount;
}
export interface AWSAccountOnboarding extends AWSAccountDetail {
  external_id: string;
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

export type ComplianceControlStatus =
  "pass" | "fail" | "not_assessed" | "error";
export interface ComplianceFramework {
  id: string;
  key: string;
  name: string;
  version: string;
  description: string;
  official_reference: string;
  enabled: boolean;
}
export interface ComplianceControl {
  id: string;
  framework_id: string;
  control_key: string;
  title: string;
  description: string;
  section: string | null;
}
export interface ComplianceAssessment {
  id: string;
  organization_id: string;
  aws_account_id: string | null;
  framework_id: string;
  evaluation_job_id: string | null;
  status: string;
  controls_total: number;
  controls_passed: number;
  controls_failed: number;
  controls_not_assessed: number;
  controls_error: number;
  findings_count: number;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
}
export interface ComplianceAssessmentControl {
  id: string;
  assessment_id: string;
  control_id: string;
  framework_id: string;
  status: ComplianceControlStatus;
  findings_count: number;
  assessed_at: string;
}
export interface RuleControlMapping {
  id: string;
  rule_key: string;
  minimum_rule_version: number;
  maximum_rule_version: number | null;
  framework_id: string;
  control_id: string;
  mapping_type: string;
  rationale: string;
}
export interface ComplianceSummary {
  assessments_total: number;
  controls_passed: number;
  controls_failed: number;
  controls_not_assessed: number;
  controls_error: number;
}
export interface ComplianceControlFindings {
  control: ComplianceControl;
  status: ComplianceControlStatus | null;
  finding_ids: string[];
  total: number;
  page: number;
  page_size: number;
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

export type RiskPriority = "critical" | "high" | "medium" | "low";
export interface RiskAssessment {
  id: string;
  organization_id: string;
  aws_account_id: string | null;
  evaluation_time: string;
  status: "pending" | "running" | "completed" | "failed";
  findings_total: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  informational_count: number;
  accounts_scored: number;
  aggregate_score: number | null;
  aggregate_priority: RiskPriority | null;
}
export interface FindingRisk {
  id: string;
  finding_id: string;
  asset_id: string | null;
  aws_account_id: string;
  risk_score: number;
  priority: RiskPriority;
  severity: FindingSeverity;
  rule_key: string;
  finding_status: FindingStatus;
  asset_name: string | null;
  service: string;
  region: string | null;
  business_impact: string;
  severity_points: number;
  exposure_points: number;
  exploitability_points: number;
  privilege_points: number;
  asset_criticality_points: number;
  environment_points: number;
  business_impact_points: number;
  data_sensitivity_points: number;
  age_points: number;
  compensating_adjustment: number;
  component_codes_json: Record<string, string>;
  unknown_inputs_json: string[];
}
export interface OrganizationRisk {
  risk_score: number;
  priority: RiskPriority;
  highest_account_score: number;
  mean_account_score: number;
  accounts_total: number;
  evaluation_time: string;
}
export interface AccountRisk {
  aws_account_id: string;
  risk_score: number;
  priority: RiskPriority;
  findings_total: number;
}
export interface RiskSummary {
  current: OrganizationRisk | null;
  assessment: RiskAssessment | null;
  highest_risk_accounts: AccountRisk[];
  highest_risk_findings: FindingRisk[];
  highest_risk_assets: FindingRisk[];
  trend: OrganizationRisk[];
}

export interface DashboardCountItem {
  key: string;
  count: number;
}
export interface DashboardMetadata {
  organization_id: string;
  generated_at: string;
  is_partial: boolean;
  missing_sections: string[];
}
export interface DashboardAccountPosture {
  total_accounts: number;
  connected_accounts: number;
  disconnected_accounts: number;
  accounts_requiring_attention: number;
}
export interface DashboardAssetInventory {
  total_assets: number;
  active_assets: number;
  inactive_assets: number;
  counts_by_type: DashboardCountItem[];
  counts_by_region: DashboardCountItem[];
}
export interface DashboardRecentFinding {
  id: string;
  aws_account_id: string;
  asset_id: string | null;
  rule_key: string;
  severity: FindingSeverity;
  status: FindingStatus;
  service: string;
  region: string | null;
  last_seen_at: string;
}
export interface DashboardFindingPosture {
  open_total: number;
  resolved_total: number;
  suppressed_total: number;
  open_by_severity: DashboardCountItem[];
  open_by_service: DashboardCountItem[];
  open_by_account: DashboardCountItem[];
  recent_critical_and_high_findings: DashboardRecentFinding[];
}
export interface DashboardCompliancePosture {
  assessment_id: string | null;
  framework_key: string | null;
  framework_name: string | null;
  framework_version: string | null;
  assessment_status: "completed" | null;
  evaluation_time: string | null;
  controls_total: number;
  passed: number;
  failed: number;
  not_assessed: number;
  error: number;
  pass_percentage: number | null;
}
export interface DashboardRiskTrendPoint {
  assessment_id: string;
  evaluation_time: string;
  aggregate_score: number;
  aggregate_priority: RiskPriority;
}
export interface DashboardAccountRiskHeatmapItem {
  aws_account_id: string;
  account_display_identifier: string;
  score: number;
  priority: RiskPriority;
  findings_total: number;
  critical_count: number;
  high_count: number;
}
export interface DashboardRiskPosture {
  assessment_id: string | null;
  evaluation_time: string | null;
  aggregate_score: number | null;
  aggregate_priority: RiskPriority | null;
  findings_total: number;
  severity_counters: DashboardCountItem[];
  highest_risk_accounts: DashboardAccountRiskHeatmapItem[];
  trend: DashboardRiskTrendPoint[];
}
export interface DashboardFreshnessItem {
  id: string | null;
  status:
    | DiscoveryStatus
    | EvaluationStatus
    | "completed"
    | "failed"
    | "pending"
    | "running"
    | null;
  started_at: string | null;
  finished_at: string | null;
  evaluation_time: string | null;
}
export interface DashboardOperationalFreshness {
  latest_completed_discovery: DashboardFreshnessItem | null;
  latest_discovery: DashboardFreshnessItem | null;
  latest_completed_evaluation: DashboardFreshnessItem | null;
  latest_evaluation: DashboardFreshnessItem | null;
  latest_completed_compliance_assessment: DashboardFreshnessItem | null;
  latest_compliance_assessment: DashboardFreshnessItem | null;
  latest_completed_risk_assessment: DashboardFreshnessItem | null;
  latest_risk_assessment: DashboardFreshnessItem | null;
}
export interface DashboardSummary {
  metadata: DashboardMetadata;
  accounts: DashboardAccountPosture;
  assets: DashboardAssetInventory;
  findings: DashboardFindingPosture;
  compliance: DashboardCompliancePosture;
  risk: DashboardRiskPosture;
  account_risk_heatmap: DashboardAccountRiskHeatmapItem[];
  freshness: DashboardOperationalFreshness;
}

export type AITaskType =
  | "explain_finding"
  | "explain_business_impact"
  | "suggest_remediation"
  | "executive_summary"
  | "jira_description"
  | "email_summary";
export interface AIContent {
  title: string;
  summary: string;
  details: string[];
  caveats: string[];
  source_references: string[];
  draft_only: boolean;
}
export interface AIRequestRecord {
  id: string;
  organization_id: string;
  requested_by_user_id: string;
  task_type: AITaskType;
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "timed_out"
    | "provider_disabled"
    | "invalid_response"
    | "rate_limited";
  provider_key: string;
  model_key: string;
  prompt_key: string;
  prompt_version: number;
  context_hash: string;
  request_fingerprint: string;
  response_schema_version: number;
  error_code: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  source_type: "finding" | "risk_assessment" | "compliance_assessment";
  source_id: string;
  source_version: number;
  source_staleness: "current" | "stale" | "source_missing";
  content: AIContent | null;
}

export type NotificationChannel = "email";
export type NotificationStatus =
  "pending_approval" | "approved" | "delivered" | "failed";
export interface NotificationEvent {
  id: string;
  organization_id: string;
  source_event_type: string;
  source_resource_type: string;
  source_resource_id: string;
  channel: NotificationChannel;
  template_key: string;
  destination_reference: string | null;
  status: NotificationStatus;
  attempt_count: number;
  approved_by_user_id: string | null;
  approved_at: string | null;
  scheduled_at: string | null;
  delivered_at: string | null;
  failed_at: string | null;
  failure_reason: string | null;
  provider_key: string | null;
  provider_message_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScanSchedule {
  id: string;
  organization_id: string;
  aws_account_id: string;
  name: string;
  interval_minutes: number;
  enabled: boolean;
  created_by_user_id: string | null;
  last_run_at: string | null;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
}
export type ScanRunTrigger = "manual" | "scheduled";
export type ScanRunStatus = "pending" | "running" | "completed" | "failed";
export interface ScanRun {
  id: string;
  organization_id: string;
  aws_account_id: string;
  schedule_id: string | null;
  trigger: ScanRunTrigger;
  status: ScanRunStatus;
  discovery_job_id: string | null;
  evaluation_job_id: string | null;
  error_summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export type RemediationStatus =
  | "pending_approval"
  | "approved"
  | "rejected"
  | "cancelled"
  | "succeeded"
  | "failed";
export type RemediationExecutionMode =
  "mock_automation" | "manual" | "jira_draft";
export interface RemediationRequest {
  id: string;
  organization_id: string;
  aws_account_id: string;
  finding_id: string;
  rule_key: string;
  rule_version: number;
  requested_by_user_id: string | null;
  approved_by_user_id: string | null;
  rejected_by_user_id: string | null;
  status: RemediationStatus;
  execution_mode: RemediationExecutionMode;
  automation_eligible: boolean;
  dry_run: boolean;
  title: string;
  summary: string;
  remediation_steps_json: string[];
  verification_steps_json: string[];
  rollback_steps_json: string[];
  before_state_json: Record<string, unknown> | null;
  after_state_json: Record<string, unknown> | null;
  execution_result_json: Record<string, unknown> | null;
  attempt_count: number;
  rejection_reason: string | null;
  failure_reason: string | null;
  requested_at: string;
  approved_at: string | null;
  rejected_at: string | null;
  cancelled_at: string | null;
  executed_at: string | null;
  failed_at: string | null;
  created_at: string;
  updated_at: string;
}
