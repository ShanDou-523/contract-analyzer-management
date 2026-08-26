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
