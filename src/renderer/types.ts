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
