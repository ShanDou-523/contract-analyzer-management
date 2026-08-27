import axios, { type AxiosInstance } from 'axios'
import { ElMessage } from 'element-plus'
import type {
  AnalysisTemplate,
  AnalysisTemplateWrite,
  DocumentDetail,
  DocumentListItem,
  Settings,
  TokenResponse,
  AuthUser,
  UserCreate,
} from '../types'

let api: AxiosInstance | null = null

async function getBaseUrl(): Promise<string> {
  return window.electronAPI
    ? await window.electronAPI.getPythonBaseUrl()
    : 'http://127.0.0.1:5768'
}

export async function initApi(): Promise<AxiosInstance> {
  if (api) return api

  api = axios.create({
    baseURL: await getBaseUrl(),
    timeout: 180000,
    headers: { 'Content-Type': 'application/json' },
  })

  api.interceptors.request.use((config) => {
    const token = localStorage.getItem('contract_analyzer_access_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  })

  api.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response) {
        const { status, data } = error.response
        const detail = data?.message || data?.detail || '未知错误'
        if (status === 401 && !window.location.hash.includes('/login')) {
          localStorage.removeItem('contract_analyzer_access_token')
          localStorage.removeItem('contract_analyzer_refresh_token')
          window.dispatchEvent(new Event('contract-analyzer-auth-expired'))
          window.location.hash = '#/login'
        }
        switch (status) {
          case 413:
            ElMessage.error(`文件过大: ${detail}`)
            break
          case 429:
            ElMessage.error('请求过于频繁，请稍后再试')
            break
          case 500:
            ElMessage.error(`服务器错误: ${detail}`)
            break
          case 502:
            ElMessage.error(`AI服务错误: ${detail}`)
            break
          case 504:
            ElMessage.error(`请求超时: ${detail}`)
            break
          default:
            ElMessage.error(`请求失败 (${status}): ${detail}`)
        }
      } else if (error.code === 'ECONNREFUSED') {
        ElMessage.error('无法连接到后端服务，请检查应用是否正常启动')
      } else if (error.code === 'ECONNABORTED') {
        ElMessage.error('请求超时，请检查网络或重试')
      } else {
        ElMessage.error(`网络错误: ${error.message}`)
      }
      return Promise.reject(error)
    },
  )

  return api
}

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await (await client()).post('/api/v1/auth/login', { username, password })
  return data
}

export async function bootstrapAdmin(payload: {
  organization_name: string
  organization_code: string
  username: string
  password: string
  display_name: string
}): Promise<TokenResponse> {
  const { data } = await (await client()).post('/api/v1/auth/bootstrap', payload)
  return data
}

export async function getCurrentUser() {
  const { data } = await (await client()).get('/api/v1/auth/me')
  return data
}

export async function logout(refreshToken: string) {
  await (await client()).post('/api/v1/auth/logout', { refresh_token: refreshToken })
}

export async function getUsers(): Promise<AuthUser[]> {
  const { data } = await (await client()).get('/api/v1/users')
  return data
}

export async function createUser(payload: UserCreate): Promise<AuthUser> {
  const { data } = await (await client()).post('/api/v1/users', payload)
  return data
}

async function client(): Promise<AxiosInstance> {
  return api || (await initApi())
}

export async function uploadPdf(file: File, templateId?: string) {
  const form = new FormData()
  form.append('file', file)
  if (templateId) form.append('template_id', templateId)
  const { data } = await (await client()).post('/api/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
  return data
}

export async function listDocuments(
  templateId?: string,
  search?: string,
): Promise<{ documents: DocumentListItem[]; total: number }> {
  const params: Record<string, string> = {}
  if (search?.trim()) params.search = search.trim()
  else if (templateId && templateId !== 'all') params.template_id = templateId
  const { data } = await (await client()).get('/api/documents', {
    params: Object.keys(params).length ? params : undefined,
  })
  return data
}

export async function assignDocumentTemplate(id: string, templateId: string | null) {
  const { data } = await (await client()).put(`/api/documents/${id}/template`, {
    template_id: templateId,
  })
  return data as DocumentListItem
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  const { data } = await (await client()).get(`/api/documents/${id}`)
  return data
}

export async function deleteDocument(id: string): Promise<void> {
  await (await client()).delete(`/api/documents/${id}`)
}

export async function runOcr(id: string) {
  const { data } = await (await client()).post(`/api/ocr/${id}/process`)
  return data
}

export async function runAnalysis(id: string, templateId?: string) {
  const { data } = await (await client()).post(`/api/analysis/${id}/analyze`, {
    template_id: templateId || null,
  })
  return data
}

export async function getAnalysisTemplates(): Promise<AnalysisTemplate[]> {
  const { data } = await (await client()).get('/api/analysis-templates')
  return data
}

export async function createAnalysisTemplate(
  template: AnalysisTemplateWrite,
): Promise<AnalysisTemplate> {
  const { data } = await (await client()).post('/api/analysis-templates', template)
  return data
}

export async function updateAnalysisTemplate(
  id: string,
  template: AnalysisTemplateWrite,
): Promise<AnalysisTemplate> {
  const { data } = await (await client()).put(`/api/analysis-templates/${id}`, template)
  return data
}

export async function deleteAnalysisTemplate(id: string): Promise<void> {
  await (await client()).delete(`/api/analysis-templates/${id}`)
}

export async function duplicateAnalysisTemplate(id: string): Promise<AnalysisTemplate> {
  const { data } = await (await client()).post(`/api/analysis-templates/${id}/duplicate`)
  return data
}

export async function setDefaultAnalysisTemplate(id: string): Promise<AnalysisTemplate> {
  const { data } = await (await client()).post(`/api/analysis-templates/${id}/set-default`)
  return data
}

export async function getSettings(): Promise<Settings> {
  const { data } = await (await client()).get('/api/settings')
  return data
}

export async function updateSettings(settings: Settings) {
  const { data } = await (await client()).put('/api/settings', settings)
  return data
}
