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
  Contract,
  ContractFile,
  ContractImportConfirm,
  ContractImportPreview,
  PagedContracts,
  Contact,
  ContractDetail,
  ContractOperation,
  ContractPartyLink,
  FulfillmentAssignee,
  FulfillmentTask,
  FulfillmentDashboard,
  FulfillmentNotification,
  NotificationStatus,
  PagedFulfillmentTasks,
  PagedNotifications,
  Party,
  ReminderScanResult,
  AnalysisRiskStatus,
  ContractAnalysisRun,
  ContractRisksOut,
  PagedRisks,
  RiskLedgerItem,
  RiskSummary,
  RiskReportOverview,
  PagedRiskContractRankings,
  BackgroundJob,
  PagedBackgroundJobs,
  PagedNotificationDeliveries,
  PagedRiskReportSnapshots,
  RiskReminderScanQueued,
  StructuredAnalysisResult,
} from '../types'

let api: AxiosInstance | null = null

async function getBaseUrl(): Promise<string> {
  return window.electronAPI
    ? await window.electronAPI.getPythonBaseUrl()
    : import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5768'
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

export async function listContracts(params: {
  page?: number
  page_size?: number
  search?: string
  status?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
} = {}): Promise<PagedContracts> {
  const { data } = await (await client()).get('/api/v1/contracts', { params })
  return data
}

export async function listRecycleBin(params: {
  page?: number
  page_size?: number
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
} = {}): Promise<PagedContracts> {
  const { data } = await (await client()).get('/api/v1/contracts/recycle-bin', { params })
  return data
}

export async function createContract(payload: Partial<Contract> & { name: string }): Promise<Contract> {
  const { data } = await (await client()).post('/api/v1/contracts', payload)
  return data
}

export async function deleteContract(id: string) {
  await (await client()).delete(`/api/v1/contracts/${id}`)
}

export async function restoreContract(id: string): Promise<Contract> {
  const { data } = await (await client()).post(`/api/v1/contracts/${id}/restore`)
  return data
}

export async function listContractFiles(contractId: string): Promise<ContractFile[]> {
  const { data } = await (await client()).get(`/api/v1/contracts/${contractId}/files`)
  return data
}

export async function uploadContractFile(contractId: string, file: File, purpose = 'original') {
  const form = new FormData()
  form.append('file', file)
  form.append('purpose', purpose)
  const { data } = await (await client()).post(`/api/v1/contracts/${contractId}/files`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
  return data
}

export async function getContractFileBlob(url: string): Promise<Blob> {
  const { data } = await (await client()).get(url, { responseType: 'blob' })
  return data
}

export async function createContractImport(file: File): Promise<ContractImportPreview> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await (await client()).post('/api/v1/contracts/imports', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
  return data
}

export async function getContractImportPreview(jobId: string): Promise<ContractImportPreview> {
  const { data } = await (await client()).get(`/api/v1/contracts/imports/${jobId}`)
  return data
}

export async function validateContractImport(jobId: string): Promise<ContractImportPreview> {
  const { data } = await (await client()).post(`/api/v1/contracts/imports/${jobId}/validate`)
  return data
}

export async function confirmContractImport(jobId: string): Promise<ContractImportConfirm> {
  const { data } = await (await client()).post(`/api/v1/contracts/imports/${jobId}/confirm`)
  return data
}

export async function getContractDetail(id: string): Promise<ContractDetail> {
  const { data } = await (await client()).get(`/api/v1/contracts/${id}/detail`)
  return data
}

export async function listContractAnalysisRuns(contractId: string): Promise<ContractAnalysisRun[]> {
  const { data } = await (await client()).get(`/api/v1/contracts/${contractId}/analysis-runs`)
  return data
}

export async function importLegacyStructuredResults(runId: string): Promise<StructuredAnalysisResult[]> {
  const { data } = await (await client()).post(`/api/v1/analysis-runs/${runId}/structured-results/import-legacy`)
  return data
}

export async function submitStructuredResult(runId: string, resultId: string): Promise<StructuredAnalysisResult> {
  const { data } = await (await client()).post(`/api/v1/analysis-runs/${runId}/structured-results/${resultId}/submit`)
  return data
}

export async function reviewStructuredResult(
  runId: string,
  resultId: string,
  decision: 'approved' | 'rejected',
  comment = '',
): Promise<StructuredAnalysisResult> {
  const { data } = await (await client()).post(`/api/v1/analysis-runs/${runId}/structured-results/${resultId}/review`, { decision, comment })
  return data
}

export async function updateStructuredRisk(
  runId: string,
  resultId: string,
  riskId: string,
  status: AnalysisRiskStatus,
  comment: string,
): Promise<StructuredAnalysisResult> {
  const { data } = await (await client()).patch(`/api/v1/analysis-runs/${runId}/structured-results/${resultId}/risks/${riskId}`, { status, comment })
  return data
}

export async function getRiskSummary(): Promise<RiskSummary> {
  const { data } = await (await client()).get('/api/v1/risks/summary')
  return data
}

export async function getRiskReportOverview(days = 30): Promise<RiskReportOverview> {
  const { data } = await (await client()).get('/api/v1/risk-reports/overview', { params: { days } })
  return data
}

export async function listRiskContractRankings(params: {
  page?: number
  page_size?: number
  days?: number
  sort_by?: 'total' | 'open' | 'critical' | 'overdue'
  sort_order?: 'asc' | 'desc'
} = {}): Promise<PagedRiskContractRankings> {
  const { data } = await (await client()).get('/api/v1/risk-reports/contracts', { params })
  return data
}

export async function scanRiskReminders(): Promise<RiskReminderScanQueued> {
  const { data } = await (await client()).post('/api/v1/risks/reminders/scan')
  return data
}

export async function downloadRiskReport(days = 30): Promise<Blob> {
  const { data } = await (await client()).get('/api/v1/risk-reports/export', {
    params: { days },
    responseType: 'blob',
  })
  return data
}

export async function listBackgroundJobs(params: {
  page?: number
  page_size?: number
  status?: string
  job_type?: string
} = {}): Promise<PagedBackgroundJobs> {
  const { data } = await (await client()).get('/api/v1/background-jobs', { params })
  return data
}

export async function retryBackgroundJob(jobId: string): Promise<BackgroundJob> {
  const { data } = await (await client()).post(`/api/v1/background-jobs/${jobId}/retry`)
  return data
}

export async function queueNotificationDispatch(): Promise<BackgroundJob> {
  const { data } = await (await client()).post('/api/v1/notification-deliveries/dispatch')
  return data
}

export async function listNotificationDeliveries(params: {
  page?: number
  page_size?: number
  status?: string
  provider_name?: string
} = {}): Promise<PagedNotificationDeliveries> {
  const { data } = await (await client()).get('/api/v1/notification-deliveries', { params })
  return data
}

export async function queueRiskReportSnapshot(): Promise<BackgroundJob> {
  const { data } = await (await client()).post('/api/v1/risk-reports/snapshots')
  return data
}

export async function listRiskReportSnapshots(params: {
  page?: number
  page_size?: number
  date_from?: string
  date_to?: string
} = {}): Promise<PagedRiskReportSnapshots> {
  const { data } = await (await client()).get('/api/v1/risk-reports/snapshots', { params })
  return data
}

export async function downloadRiskReportSnapshots(params: {
  date_from?: string
  date_to?: string
} = {}): Promise<Blob> {
  const { data } = await (await client()).get('/api/v1/risk-reports/snapshots/export', {
    params,
    responseType: 'blob',
  })
  return data
}

export async function listRisks(params: {
  page?: number
  page_size?: number
  search?: string
  status?: string
  severity?: string
  contract_id?: string
  assignee_id?: string
  overdue_only?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
} = {}): Promise<PagedRisks> {
  const { data } = await (await client()).get('/api/v1/risks', { params })
  return data
}

export async function listContractRisks(contractId: string, params: { page?: number; page_size?: number } = {}): Promise<ContractRisksOut> {
  const { data } = await (await client()).get(`/api/v1/contracts/${contractId}/risks`, { params })
  return data
}

export async function updateRiskRemediation(
  riskId: string,
  payload: {
    status?: string
    assignee_id?: string | null
    remediation_due_at?: string | null
    remediation_notes?: string | null
    comment?: string
  },
): Promise<RiskLedgerItem> {
  const { data } = await (await client()).patch(`/api/v1/risks/${riskId}`, payload)
  return data
}

export async function listFulfillmentAssignees(): Promise<FulfillmentAssignee[]> {
  const { data } = await (await client()).get('/api/v1/fulfillment-assignees')
  return data
}

export async function listParties(params: { party_type?: string; search?: string } = {}): Promise<Party[]> {
  const { data } = await (await client()).get('/api/v1/parties', { params })
  return data
}

export async function createParty(payload: {
  name: string
  party_type: 'party_a' | 'party_b' | 'other'
  tax_no?: string
  address?: string
  phone?: string
  email?: string
}): Promise<Party> {
  const { data } = await (await client()).post('/api/v1/parties', payload)
  return data
}

export async function linkContractParty(contractId: string, payload: { party_id: string; role: string; notes?: string }): Promise<ContractPartyLink> {
  const { data } = await (await client()).post(`/api/v1/contracts/${contractId}/parties`, payload)
  return data
}

export async function unlinkContractParty(contractId: string, linkId: string) {
  await (await client()).delete(`/api/v1/contracts/${contractId}/parties/${linkId}`)
}

export async function createPartyContact(partyId: string, payload: {
  name: string
  title?: string
  phone?: string
  email?: string
  is_primary?: boolean
}): Promise<Contact> {
  const { data } = await (await client()).post(`/api/v1/parties/${partyId}/contacts`, payload)
  return data
}

export async function updatePartyContact(partyId: string, contactId: string, payload: Partial<Contact>): Promise<Contact> {
  const { data } = await (await client()).put(`/api/v1/parties/${partyId}/contacts/${contactId}`, payload)
  return data
}

export async function createFulfillmentTask(contractId: string, payload: {
  title: string
  description?: string
  task_type?: string
  priority?: string
  assignee_id?: string
  due_at: string
  remind_at?: string
}): Promise<FulfillmentTask> {
  const { data } = await (await client()).post(`/api/v1/contracts/${contractId}/tasks`, payload)
  return data
}

export async function updateFulfillmentTask(contractId: string, taskId: string, payload: Partial<FulfillmentTask>): Promise<FulfillmentTask> {
  const { data } = await (await client()).patch(`/api/v1/contracts/${contractId}/tasks/${taskId}`, payload)
  return data
}

export async function listContractOperations(contractId: string): Promise<ContractOperation[]> {
  const { data } = await (await client()).get(`/api/v1/contracts/${contractId}/operations`)
  return data
}

export async function getFulfillmentDashboard(): Promise<FulfillmentDashboard> {
  const { data } = await (await client()).get('/api/v1/fulfillment/dashboard')
  return data
}

export async function listFulfillmentTasks(params: {
  page?: number
  page_size?: number
  search?: string
  status?: string
  priority?: string
  assignee_id?: string
  overdue_only?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
} = {}): Promise<PagedFulfillmentTasks> {
  const { data } = await (await client()).get('/api/v1/fulfillment/tasks', { params })
  return data
}

export async function scanFulfillmentReminders(): Promise<ReminderScanResult> {
  const { data } = await (await client()).post('/api/v1/fulfillment/reminders/scan')
  return data
}

export async function listNotifications(params: {
  page?: number
  page_size?: number
  status?: NotificationStatus | ''
  notification_type?: string
} = {}): Promise<PagedNotifications> {
  const { data } = await (await client()).get('/api/v1/notifications', { params })
  return data
}

export async function updateNotificationStatus(
  notificationId: string,
  status: Exclude<NotificationStatus, 'unread'>,
): Promise<FulfillmentNotification> {
  const { data } = await (await client()).patch(`/api/v1/notifications/${notificationId}`, { status })
  return data
}

export async function markAllNotificationsRead(): Promise<{ updated: number }> {
  const { data } = await (await client()).post('/api/v1/notifications/read-all')
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
