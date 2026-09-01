export interface AnalysisResult {
  id: string
  document_id: string
  prompt_type: string
  prompt_text: string
  response_text: string | null
  tokens_used: number | null
  template_id: string | null
  template_name: string | null
  template_version: number | null
  fields_snapshot: AnalysisField[] | null
  created_at: string | null
}

export interface AnalysisField {
  id: string
  key: string
  label: string
  instruction: string
  enabled: boolean
}

export interface AnalysisTemplateWrite {
  name: string
  description: string
  analysis_focus: string
  fields: AnalysisField[]
  review_enabled: boolean
  review_instructions: string
}

export interface AnalysisTemplate extends AnalysisTemplateWrite {
  id: string
  version: number
  is_default: boolean
  document_count: number
  created_at: string | null
  updated_at: string | null
}

export interface DocumentListItem {
  id: string
  original_filename: string
  file_size: number
  status: string
  page_count: number | null
  created_at: string | null
  analysis_template_id: string | null
  analysis_template_name: string | null
  analysis_template_version: number | null
}

export interface DocumentDetail extends DocumentListItem {
  stored_filename: string
  ocr_text: string | null
  ocr_pages_detail: string | null
  error_message: string | null
  updated_at: string | null
  analysis_results: AnalysisResult[]
}

export interface Settings {
  deepseek_api_key: string
  baidu_ocr_api_key: string
  baidu_ocr_secret_key: string
}

export interface AuthUser {
  id: string
  username: string
  display_name: string
  email: string | null
  organization_id: string
  status: string
  roles: string[]
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_at: string
  user: AuthUser
}

export interface UserCreate {
  username: string
  password: string
  display_name: string
  email?: string
  roles: string[]
}

export interface Contract {
  id: string
  organization_id: string
  contract_no: string | null
  name: string
  category: string | null
  status: string
  party_a_name: string | null
  party_b_name: string | null
  project_name: string | null
  department_name: string | null
  sign_date: string | null
  effective_date: string | null
  start_date: string | null
  end_date: string | null
  amount: string | number | null
  currency: string
  tax_included: boolean | null
  risk_level: string
  source: string
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export interface PagedContracts {
  items: Contract[]
  total: number
  page: number
  page_size: number
}

export interface FileVersion {
  id: string
  contract_file_id: string
  version_no: number
  original_filename: string
  mime_type: string
  size_bytes: number
  sha256: string | null
  page_count: number | null
  uploaded_at: string
  is_current: boolean
  download_url: string
  preview_url: string
}

export interface ContractFile {
  id: string
  contract_id: string
  purpose: string
  current_version_id: string | null
  versions: FileVersion[]
}

export interface ContractImportPreview {
  id: string
  original_filename: string
  file_format: string
  columns: string[]
  sample_rows: Record<string, string>[]
  row_count: number
  status: string
  validation: {
    valid?: boolean
    errors?: Array<{ row: number; field: string; message: string }>
    valid_rows?: number
  }
  expires_at: string | null
}

export interface ContractImportConfirm {
  job_id: string
  created_count: number
  contract_ids: string[]
}

export type PartyType = 'party_a' | 'party_b' | 'other'
export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled'

export interface Party {
  id: string
  organization_id: string
  party_type: PartyType
  name: string
  tax_no: string | null
  address: string | null
  phone: string | null
  email: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface Contact {
  id: string
  organization_id: string
  party_id: string
  name: string
  title: string | null
  phone: string | null
  email: string | null
  is_primary: boolean
  status: string
  created_at: string
  updated_at: string
}

export interface FulfillmentAssignee {
  id: string
  display_name: string
}

export interface ContractPartyLink {
  id: string
  contract_id: string
  role: PartyType
  notes: string
  party: Party
  contacts: Contact[]
}

export interface FulfillmentTask {
  id: string
  organization_id: string
  contract_id: string
  title: string
  description: string
  task_type: string
  status: TaskStatus
  priority: 'low' | 'medium' | 'high' | 'critical'
  assignee_id: string | null
  due_at: string
  remind_at: string | null
  completed_at: string | null
  completed_by: string | null
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
  is_overdue: boolean
}

export interface ContractOperation {
  id: string
  action: string
  resource_type: string | null
  resource_id: string | null
  details: Record<string, unknown>
  user_id: string | null
  created_at: string
}

export interface ContractDetail {
  contract: Contract
  files: ContractFile[]
  parties: ContractPartyLink[]
  tasks: FulfillmentTask[]
  operations: ContractOperation[]
}

export interface FulfillmentTaskListItem extends FulfillmentTask {
  contract_name: string
  contract_no: string | null
  assignee_name: string | null
}

export interface PagedFulfillmentTasks {
  items: FulfillmentTaskListItem[]
  total: number
  page: number
  page_size: number
}

export interface AssigneeWorkload {
  assignee_id: string | null
  assignee_name: string
  open_count: number
  overdue_count: number
}

export interface FulfillmentDashboard {
  generated_at: string
  total_open: number
  pending: number
  in_progress: number
  overdue: number
  due_today: number
  due_next_7_days: number
  unassigned: number
  completed_last_30_days: number
  unread_notifications: number
  status_counts: Array<{ status: TaskStatus; count: number }>
  priority_counts: Array<{ priority: FulfillmentTask['priority']; count: number }>
  assignee_workloads: AssigneeWorkload[]
  upcoming_tasks: FulfillmentTaskListItem[]
}

export type NotificationStatus = 'unread' | 'read' | 'ignored'
export type NotificationType = 'reminder' | 'overdue' | 'risk_reminder' | 'risk_overdue'

export interface FulfillmentNotification {
  id: string
  organization_id: string
  recipient_id: string
  contract_id: string
  contract_name: string
  contract_no: string | null
  task_id: string | null
  task_title: string | null
  risk_id: string | null
  risk_title: string | null
  remediation_due_at: string | null
  notification_type: NotificationType
  status: NotificationStatus
  title: string
  message: string
  source_at: string
  generated_at: string
  read_at: string | null
  ignored_at: string | null
}

export interface PagedNotifications {
  items: FulfillmentNotification[]
  total: number
  unread: number
  page: number
  page_size: number
}

export interface ReminderScanResult {
  examined_tasks: number
  created: number
  skipped_existing: number
  skipped_without_recipient: number
}

export type StructuredAnalysisStatus = 'draft' | 'in_review' | 'approved' | 'rejected' | 'superseded'
export type AnalysisRiskSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AnalysisRiskStatus = 'open' | 'in_progress' | 'accepted' | 'mitigated' | 'dismissed' | 'closed'

export interface StructuredAnalysisField {
  id: string
  field_key: string
  label: string
  value: unknown
  value_text: string
  confidence: number | null
  position: number
}

export interface AnalysisEvidence {
  id: string
  file_version_id: string
  page_no: number | null
  char_start: number | null
  char_end: number | null
  quote: string
  locator: Record<string, unknown>
  created_at: string
}

export interface StructuredAnalysisRisk {
  id: string
  evidence_id: string | null
  code: string | null
  title: string
  description: string
  severity: AnalysisRiskSeverity
  status: AnalysisRiskStatus
  assignee_id: string | null
  remediation_due_at: string | null
  remediation_notes: string | null
  reviewer_comment: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  closed_by: string | null
  closed_at: string | null
  closure_comment: string | null
  is_overdue: boolean
  created_at: string
}

export interface StructuredAnalysisResult {
  id: string
  organization_id: string
  contract_id: string
  analysis_run_id: string
  source_result_id: string | null
  file_version_id: string
  template_version_id: string
  prompt_type: string
  version: number
  status: StructuredAnalysisStatus
  summary: string
  created_by: string
  reviewed_by: string | null
  review_comment: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
  fields: StructuredAnalysisField[]
  evidence: AnalysisEvidence[]
  risks: StructuredAnalysisRisk[]
}

export interface ContractAnalysisRun {
  id: string
  contract_id: string
  contract_name: string
  contract_no: string | null
  file_version_id: string | null
  file_name: string | null
  template_version_id: string | null
  template_name: string | null
  template_version: number | null
  task_type: string
  status: string
  provider_name: string | null
  model_name: string | null
  requested_by: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  raw_result_count: number
  structured_results: StructuredAnalysisResult[]
}

export interface RiskLedgerItem extends StructuredAnalysisRisk {
  organization_id: string
  contract_id: string
  contract_name: string
  contract_no: string | null
  structured_result_id: string
  prompt_type: string
  result_version: number
  assignee_name: string | null
  updated_at: string
}

export interface PagedRisks {
  items: RiskLedgerItem[]
  total: number
  page: number
  page_size: number
}

export interface RiskCount {
  key: string
  count: number
}

export interface RiskSummary {
  total: number
  open: number
  in_progress: number
  accepted: number
  mitigated: number
  dismissed: number
  closed: number
  overdue: number
  by_severity: RiskCount[]
  by_status: RiskCount[]
}

export interface ContractRiskSummary extends RiskSummary {
  contract_id: string
  contract_name: string
  contract_no: string | null
}

export interface ContractRisksOut {
  summary: ContractRiskSummary
  items: RiskLedgerItem[]
}

export interface RiskTrendPoint {
  date: string
  total: number
  open: number
  overdue: number
  closed: number
}

export interface RiskContractRanking {
  contract_id: string
  contract_name: string
  contract_no: string | null
  total: number
  open: number
  critical: number
  overdue: number
}

export interface RiskAssigneeWorkload {
  assignee_id: string | null
  assignee_name: string
  total: number
  open: number
  overdue: number
  closed: number
}

export interface RiskReportOverview {
  generated_at: string
  period_days: number
  summary: RiskSummary
  trend: RiskTrendPoint[]
  contract_rankings: RiskContractRanking[]
  assignee_workloads: RiskAssigneeWorkload[]
}

export interface RiskReminderScanQueued {
  status: 'queued'
}

export interface PagedRiskContractRankings {
  items: RiskContractRanking[]
  total: number
  page: number
  page_size: number
}

export type BackgroundJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export interface BackgroundJob {
  id: string
  organization_id: string
  job_type: string
  status: BackgroundJobStatus
  priority: number
  payload: Record<string, unknown>
  result: Record<string, unknown>
  attempts: number
  max_attempts: number
  available_at: string
  locked_at: string | null
  locked_by: string | null
  started_at: string | null
  finished_at: string | null
  requested_by: string | null
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface PagedBackgroundJobs {
  items: BackgroundJob[]
  total: number
  page: number
  page_size: number
}

export type NotificationDeliveryStatus = 'queued' | 'delivering' | 'sent' | 'failed'

export interface NotificationDelivery {
  id: string
  organization_id: string
  notification_id: string
  notification_title: string
  recipient_id: string
  recipient_name: string
  background_job_id: string | null
  provider_name: string
  channel: string
  status: NotificationDeliveryStatus
  attempt_count: number
  max_attempts: number
  last_error: string | null
  provider_message_id: string | null
  next_retry_at: string | null
  sent_at: string | null
  created_at: string
  updated_at: string
}

export interface PagedNotificationDeliveries {
  items: NotificationDelivery[]
  total: number
  page: number
  page_size: number
}

export interface RiskReportSnapshot {
  id: string
  organization_id: string
  snapshot_date: string
  total: number
  active: number
  overdue: number
  closed: number
  critical: number
  overdue_rate: number
  contract_rankings: RiskContractRanking[]
  assignee_workloads: RiskAssigneeWorkload[]
  source_job_id: string | null
  generated_at: string
}

export interface PagedRiskReportSnapshots {
  items: RiskReportSnapshot[]
  total: number
  page: number
  page_size: number
}

export type BatchImportStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed' | 'cancelled'
export type BatchImportItemStatus = 'queued' | 'ocr_processing' | 'ocr_done' | 'analyzing' | 'done' | 'error'

export interface BatchImportItem {
  id: string
  batch_id: string
  organization_id: string
  document_id: string | null
  original_filename: string
  file_size: number
  status: BatchImportItemStatus
  stage: 'ocr' | 'analysis'
  progress: number
  ocr_job_id: string | null
  analysis_job_id: string | null
  retry_count: number
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface BatchImport {
  id: string
  organization_id: string
  created_by: string
  template_id: string | null
  status: BatchImportStatus
  total_count: number
  completed_count: number
  failed_count: number
  progress: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  updated_at: string
  items: BatchImportItem[]
}

export interface PagedBatchImports {
  items: BatchImport[]
  total: number
  page: number
  page_size: number
}
