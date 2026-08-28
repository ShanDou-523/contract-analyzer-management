<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, Plus, Refresh, UserFilled } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import {
  createFulfillmentTask,
  createParty,
  createPartyContact,
  getContractDetail,
  importLegacyStructuredResults,
  linkContractParty,
  listContractAnalysisRuns,
  listFulfillmentAssignees,
  listParties,
  unlinkContractParty,
  reviewStructuredResult,
  submitStructuredResult,
  updateStructuredRisk,
  updateFulfillmentTask,
} from '../api'
import type {
  AnalysisRiskStatus,
  ContractAnalysisRun,
  ContractDetail,
  FulfillmentAssignee,
  FulfillmentTask,
  Party,
  PartyType,
  StructuredAnalysisResult,
  StructuredAnalysisRisk,
  TaskStatus,
} from '../types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const contractId = computed(() => String(route.params.id))
const detail = ref<ContractDetail | null>(null)
const loading = ref(false)
const partyDialog = ref(false)
const contactDialog = ref(false)
const taskDialog = ref(false)
const saving = ref(false)
const analysisSaving = ref(false)
const analysisRuns = ref<ContractAnalysisRun[]>([])
const selectedRunId = ref('')
const parties = ref<Party[]>([])
const users = ref<FulfillmentAssignee[]>([])
const selectedPartyId = ref('')
const selectedPartyForContact = ref<Party | null>(null)
const partyMode = ref<'existing' | 'new'>('existing')
const partyForm = reactive({ name: '', party_type: 'party_a' as PartyType, tax_no: '', phone: '', email: '', role: 'party_a' as PartyType, notes: '' })
const contactForm = reactive({ name: '', title: '', phone: '', email: '', is_primary: true })
const taskForm = reactive({ title: '', description: '', task_type: 'other', priority: 'medium', assignee_id: '', due_at: '', remind_at: '' })

const pendingTasks = computed(() => detail.value?.tasks.filter((task) => !['completed', 'cancelled'].includes(task.status)).length || 0)
const overdueTasks = computed(() => detail.value?.tasks.filter((task) => task.is_overdue).length || 0)
const canManage = computed(() => auth.user?.roles.some((role) => ['system_admin', 'org_admin', 'contract_manager'].includes(role)) || false)
const canStructure = computed(() => auth.user?.roles.some((role) => ['system_admin', 'org_admin', 'contract_manager', 'reviewer'].includes(role)) || false)
const canReview = computed(() => auth.user?.roles.some((role) => ['system_admin', 'org_admin', 'reviewer'].includes(role)) || false)
const selectedAnalysisRun = computed(() => analysisRuns.value.find((run) => run.id === selectedRunId.value) || null)

async function loadDetail() {
  loading.value = true
  try {
    detail.value = await getContractDetail(contractId.value)
  } finally {
    loading.value = false
  }
}

async function loadAnalysisRuns() {
  analysisRuns.value = await listContractAnalysisRuns(contractId.value)
  if (!analysisRuns.value.some((run) => run.id === selectedRunId.value)) {
    selectedRunId.value = analysisRuns.value[0]?.id || ''
  }
}

async function loadPage() {
  loading.value = true
  try {
    await Promise.all([getContractDetail(contractId.value), listContractAnalysisRuns(contractId.value)]).then(([contract, runs]) => {
      detail.value = contract
      analysisRuns.value = runs
      if (!runs.some((run) => run.id === selectedRunId.value)) selectedRunId.value = runs[0]?.id || ''
    })
  } finally {
    loading.value = false
  }
}

async function importStructuredResults() {
  if (!selectedAnalysisRun.value) return
  analysisSaving.value = true
  try {
    await importLegacyStructuredResults(selectedAnalysisRun.value.id)
    await loadAnalysisRuns()
    ElMessage.success('原始分析结果已转换为结构化草稿')
  } finally {
    analysisSaving.value = false
  }
}

async function submitAnalysisResult(result: StructuredAnalysisResult) {
  await ElMessageBox.confirm(`提交“${promptTypeLabel(result.prompt_type)}”第 ${result.version} 版复核？`, '提交复核', { type: 'warning' })
  analysisSaving.value = true
  try {
    await submitStructuredResult(result.analysis_run_id, result.id)
    await loadAnalysisRuns()
    ElMessage.success('已提交复核')
  } finally {
    analysisSaving.value = false
  }
}

async function reviewAnalysisResult(result: StructuredAnalysisResult, decision: 'approved' | 'rejected') {
  let comment = ''
  if (decision === 'rejected') {
    const response = await ElMessageBox.prompt('请填写需要修订的内容', '驳回复核', {
      inputType: 'textarea', inputValidator: (value) => Boolean(value.trim()) || '驳回意见不能为空',
    })
    comment = response.value
  } else {
    await ElMessageBox.confirm('确认批准当前结构化结果？批准后不可直接修改。', '批准复核', { type: 'success' })
  }
  analysisSaving.value = true
  try {
    await reviewStructuredResult(result.analysis_run_id, result.id, decision, comment)
    await loadAnalysisRuns()
    ElMessage.success(decision === 'approved' ? '复核已批准' : '结果已驳回')
  } finally {
    analysisSaving.value = false
  }
}

async function reviewRisk(result: StructuredAnalysisResult, risk: StructuredAnalysisRisk, status: AnalysisRiskStatus) {
  const response = await ElMessageBox.prompt('请记录风险判断或处置依据', '处置风险项', {
    inputType: 'textarea', inputValidator: (value) => Boolean(value.trim()) || '复核意见不能为空',
  })
  analysisSaving.value = true
  try {
    await updateStructuredRisk(result.analysis_run_id, result.id, risk.id, status, response.value)
    await loadAnalysisRuns()
    ElMessage.success('风险项状态已更新')
  } finally {
    analysisSaving.value = false
  }
}

async function openPartyDialog() {
  partyDialog.value = true
  parties.value = await listParties()
}

async function savePartyLink() {
  saving.value = true
  try {
    let partyId = selectedPartyId.value
    if (partyMode.value === 'new') {
      const party = await createParty({
        name: partyForm.name.trim(), party_type: partyForm.party_type,
        tax_no: partyForm.tax_no || undefined, phone: partyForm.phone || undefined, email: partyForm.email || undefined,
      })
      partyId = party.id
    }
    if (!partyId) {
      ElMessage.warning('请选择或创建主体')
      return
    }
    await linkContractParty(contractId.value, { party_id: partyId, role: partyForm.role, notes: partyForm.notes })
    partyDialog.value = false
    await loadDetail()
    ElMessage.success('合同主体已关联')
  } finally {
    saving.value = false
  }
}

async function removeParty(linkId: string) {
  await unlinkContractParty(contractId.value, linkId)
  await loadDetail()
  ElMessage.success('主体关联已解除')
}

function openContactDialog(party: Party) {
  selectedPartyForContact.value = party
  Object.assign(contactForm, { name: '', title: '', phone: '', email: '', is_primary: true })
  contactDialog.value = true
}

async function saveContact() {
  if (!selectedPartyForContact.value || !contactForm.name.trim()) return
  saving.value = true
  try {
    await createPartyContact(selectedPartyForContact.value.id, {
      name: contactForm.name.trim(), title: contactForm.title || undefined,
      phone: contactForm.phone || undefined, email: contactForm.email || undefined,
      is_primary: contactForm.is_primary,
    })
    contactDialog.value = false
    await loadDetail()
  } finally {
    saving.value = false
  }
}

function openTaskDialog() {
  Object.assign(taskForm, { title: '', description: '', task_type: 'other', priority: 'medium', assignee_id: '', due_at: '', remind_at: '' })
  taskDialog.value = true
}

async function saveTask() {
  if (!taskForm.title.trim() || !taskForm.due_at) {
    ElMessage.warning('请填写任务名称和截止时间')
    return
  }
  saving.value = true
  try {
    await createFulfillmentTask(contractId.value, {
      title: taskForm.title.trim(), description: taskForm.description,
      task_type: taskForm.task_type, priority: taskForm.priority,
      assignee_id: taskForm.assignee_id || undefined,
      due_at: new Date(taskForm.due_at).toISOString(),
      remind_at: taskForm.remind_at ? new Date(taskForm.remind_at).toISOString() : undefined,
    })
    taskDialog.value = false
    await loadDetail()
    ElMessage.success('履约任务已创建')
  } finally {
    saving.value = false
  }
}

async function changeTaskStatus(task: FulfillmentTask, status: TaskStatus) {
  await updateFulfillmentTask(contractId.value, task.id, { status })
  await loadDetail()
}

function nextStatuses(task: FulfillmentTask): Array<{ label: string; value: TaskStatus }> {
  const map: Record<TaskStatus, Array<{ label: string; value: TaskStatus }>> = {
    pending: [{ label: '开始执行', value: 'in_progress' }, { label: '取消', value: 'cancelled' }],
    in_progress: [{ label: '标记完成', value: 'completed' }, { label: '退回待处理', value: 'pending' }, { label: '取消', value: 'cancelled' }],
    completed: [],
    cancelled: [{ label: '重新打开', value: 'pending' }],
  }
  return map[task.status]
}

function userName(id: string | null) {
  return users.value.find((user) => user.id === id)?.display_name || (id ? '未知用户' : '未分配')
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function promptTypeLabel(value: string) {
  return { attribute_extraction: '合同要素', reasonability_check: '合理性审查' }[value] || value
}

function structuredStatusLabel(value: string) {
  return { draft: '草稿', in_review: '待复核', approved: '已批准', rejected: '已驳回', superseded: '已替代' }[value] || value
}

function riskStatusLabel(value: AnalysisRiskStatus) {
  return { open: '待处置', accepted: '接受风险', mitigated: '已缓释', dismissed: '已排除' }[value]
}

function severityLabel(value: string) {
  return { low: '低', medium: '中', high: '高', critical: '严重' }[value] || value
}

function formatStructuredValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}

function evidencePosition(evidence: { page_no: number | null; char_start: number | null; char_end: number | null }) {
  const page = evidence.page_no ? `第 ${evidence.page_no} 页` : '页码未标注'
  const offset = evidence.char_start !== null ? `字符 ${evidence.char_start}-${evidence.char_end ?? '?'}` : '未标注字符位置'
  return `${page} · ${offset}`
}

function actionLabel(action: string) {
  const labels: Record<string, string> = {
    'contract.created': '创建合同', 'contract.file_uploaded': '上传文件版本',
    'contract.party_linked': '关联合同主体', 'contract.party_unlinked': '解除主体关联',
    'party.created': '创建主体', 'party.updated': '更新主体',
    'contact.created': '创建联系人', 'contact.updated': '更新联系人',
    'contract.task_created': '创建履约任务', 'contract.task_updated': '更新履约任务',
  }
  return labels[action] || action
}

function partyRoleLabel(role: PartyType) {
  return { party_a: '甲方', party_b: '乙方', other: '其他' }[role]
}

function taskStatusLabel(status: TaskStatus) {
  return { pending: '待处理', in_progress: '进行中', completed: '已完成', cancelled: '已取消' }[status]
}

function contractStatusLabel(status: string) {
  return { draft: '草稿', active: '履行中', expired: '已到期', terminated: '已终止' }[status] || status
}

onMounted(async () => {
  await Promise.all([loadPage(), listFulfillmentAssignees().then((value) => { users.value = value })])
})
</script>

<template>
  <div v-loading="loading" class="detail-view">
    <div class="detail-header">
      <div>
        <el-button text :icon="ArrowLeft" @click="router.push('/contracts')">返回台账</el-button>
        <h2>{{ detail?.contract.name || '合同详情' }}</h2>
        <span class="subtitle">{{ detail?.contract.contract_no || '未设置合同编号' }}</span>
      </div>
      <el-button :icon="Refresh" @click="loadPage">刷新</el-button>
    </div>

    <template v-if="detail">
      <section class="summary-band">
        <div><span>合同状态</span><strong>{{ contractStatusLabel(detail.contract.status) }}</strong></div>
        <div><span>合同金额</span><strong>{{ detail.contract.amount ?? '-' }} {{ detail.contract.currency }}</strong></div>
        <div><span>待办任务</span><strong>{{ pendingTasks }}</strong></div>
        <div><span>逾期任务</span><strong :class="{ danger: overdueTasks }">{{ overdueTasks }}</strong></div>
        <div><span>文件版本</span><strong>{{ detail.files.reduce((sum, file) => sum + file.versions.length, 0) }}</strong></div>
      </section>

      <el-tabs>
        <el-tab-pane label="概览">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="甲方">{{ detail.contract.party_a_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="乙方">{{ detail.contract.party_b_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="项目">{{ detail.contract.project_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="归属部门">{{ detail.contract.department_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="签署日期">{{ detail.contract.sign_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="履约期间">{{ detail.contract.start_date || '-' }} 至 {{ detail.contract.end_date || '-' }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>

        <el-tab-pane :label="`主体与联系人 (${detail.parties.length})`">
          <div class="pane-toolbar"><span>{{ detail.parties.length }} 个关联主体</span><el-button v-if="canManage" type="primary" :icon="Plus" @click="openPartyDialog">关联主体</el-button></div>
          <el-table :data="detail.parties" stripe>
            <el-table-column label="角色" width="100"><template #default="{ row }"><el-tag>{{ partyRoleLabel(row.role) }}</el-tag></template></el-table-column>
            <el-table-column label="主体" min-width="220"><template #default="{ row }"><strong>{{ row.party.name }}</strong><div class="muted">{{ row.party.tax_no || '未填写税号' }}</div></template></el-table-column>
            <el-table-column label="联系人" min-width="260"><template #default="{ row }"><div v-for="contact in row.contacts" :key="contact.id">{{ contact.name }} · {{ contact.phone || contact.email || '-' }} <el-tag v-if="contact.is_primary" size="small" type="success">主要</el-tag></div><span v-if="!row.contacts.length" class="muted">暂无联系人</span></template></el-table-column>
            <el-table-column v-if="canManage" label="操作" width="190"><template #default="{ row }"><el-button text :icon="UserFilled" @click="openContactDialog(row.party)">联系人</el-button><el-button text type="danger" @click="removeParty(row.id)">解除</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`结构化分析 (${analysisRuns.length})`">
          <div class="pane-toolbar analysis-toolbar">
            <el-select v-model="selectedRunId" placeholder="选择分析运行" class="run-select">
              <el-option v-for="run in analysisRuns" :key="run.id" :value="run.id" :label="`${formatDate(run.created_at)} · ${run.template_name || '未命名方案'}`" />
            </el-select>
            <el-button v-if="canStructure && selectedAnalysisRun?.raw_result_count" type="primary" :loading="analysisSaving" @click="importStructuredResults">生成结构化草稿</el-button>
          </div>
          <el-empty v-if="!analysisRuns.length" description="暂无可复核的分析运行" />
          <template v-else-if="selectedAnalysisRun">
            <div class="analysis-meta">
              <span>文件：{{ selectedAnalysisRun.file_name || '未关联' }}</span>
              <span>方案：{{ selectedAnalysisRun.template_name || '未关联' }}<template v-if="selectedAnalysisRun.template_version"> v{{ selectedAnalysisRun.template_version }}</template></span>
              <span>运行状态：{{ selectedAnalysisRun.status }}</span>
              <span>原始结果：{{ selectedAnalysisRun.raw_result_count }}</span>
            </div>
            <el-empty v-if="!selectedAnalysisRun.structured_results.length" description="该运行尚无结构化结果" />
            <article v-for="result in selectedAnalysisRun.structured_results" :key="result.id" class="analysis-result">
              <header class="result-header">
                <div><h3>{{ promptTypeLabel(result.prompt_type) }}</h3><span class="muted">第 {{ result.version }} 版 · {{ formatDate(result.updated_at) }}</span></div>
                <div class="result-actions">
                  <el-tag :type="result.status === 'approved' ? 'success' : result.status === 'rejected' ? 'danger' : result.status === 'in_review' ? 'warning' : 'info'">{{ structuredStatusLabel(result.status) }}</el-tag>
                  <el-button v-if="canStructure && ['draft', 'rejected'].includes(result.status)" type="primary" plain :loading="analysisSaving" @click="submitAnalysisResult(result)">提交复核</el-button>
                  <template v-if="canReview && result.status === 'in_review'">
                    <el-button type="success" plain :loading="analysisSaving" @click="reviewAnalysisResult(result, 'approved')">批准</el-button>
                    <el-button type="danger" plain :loading="analysisSaving" @click="reviewAnalysisResult(result, 'rejected')">驳回</el-button>
                  </template>
                </div>
              </header>
              <p v-if="result.summary" class="result-summary">{{ result.summary }}</p>
              <section class="result-section">
                <h4>结构化字段 <span>{{ result.fields.length }}</span></h4>
                <el-table :data="result.fields" size="small" empty-text="暂无结构化字段">
                  <el-table-column prop="label" label="字段" min-width="180" />
                  <el-table-column label="值" min-width="360"><template #default="{ row }"><pre class="field-value">{{ formatStructuredValue(row.value) }}</pre></template></el-table-column>
                  <el-table-column label="置信度" width="100"><template #default="{ row }">{{ row.confidence === null ? '-' : `${Math.round(row.confidence * 100)}%` }}</template></el-table-column>
                </el-table>
              </section>
              <section class="result-section">
                <h4>证据定位 <span>{{ result.evidence.length }}</span></h4>
                <el-table :data="result.evidence" size="small" empty-text="暂无证据定位">
                  <el-table-column label="位置" width="210"><template #default="{ row }">{{ evidencePosition(row) }}</template></el-table-column>
                  <el-table-column prop="quote" label="原文摘录" min-width="420" show-overflow-tooltip />
                </el-table>
              </section>
              <section class="result-section">
                <h4>风险复核 <span>{{ result.risks.length }}</span></h4>
                <el-table :data="result.risks" size="small" empty-text="暂无风险项">
                  <el-table-column label="等级" width="90"><template #default="{ row }"><el-tag :type="row.severity === 'critical' ? 'danger' : row.severity === 'high' ? 'warning' : row.severity === 'low' ? 'info' : 'primary'" size="small">{{ severityLabel(row.severity) }}</el-tag></template></el-table-column>
                  <el-table-column label="风险项" min-width="260"><template #default="{ row }"><strong>{{ row.title }}</strong><div class="muted">{{ row.description || '-' }}</div></template></el-table-column>
                  <el-table-column label="处置状态" width="130"><template #default="{ row }"><el-tag :type="row.status === 'open' ? 'danger' : row.status === 'mitigated' ? 'success' : 'info'" size="small">{{ riskStatusLabel(row.status) }}</el-tag></template></el-table-column>
                  <el-table-column label="复核意见" min-width="220"><template #default="{ row }">{{ row.reviewer_comment || '-' }}</template></el-table-column>
                  <el-table-column v-if="canReview && result.status === 'in_review'" label="操作" width="130"><template #default="{ row }"><el-dropdown trigger="click" @command="(status: AnalysisRiskStatus) => reviewRisk(result, row, status)"><el-button text type="primary">处置</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item command="accepted">接受风险</el-dropdown-item><el-dropdown-item command="mitigated">标记已缓释</el-dropdown-item><el-dropdown-item command="dismissed">排除风险</el-dropdown-item></el-dropdown-menu></template></el-dropdown></template></el-table-column>
                </el-table>
              </section>
              <el-alert v-if="result.review_comment" :title="`复核意见：${result.review_comment}`" :type="result.status === 'rejected' ? 'error' : 'success'" :closable="false" show-icon />
            </article>
          </template>
        </el-tab-pane>

        <el-tab-pane :label="`履约任务 (${detail.tasks.length})`">
          <div class="pane-toolbar"><span>{{ detail.tasks.length }} 个履约任务</span><el-button v-if="canManage" type="primary" :icon="Plus" @click="openTaskDialog">新建任务</el-button></div>
          <el-table :data="detail.tasks" stripe>
            <el-table-column label="任务" min-width="220"><template #default="{ row }"><strong>{{ row.title }}</strong><div class="muted">{{ row.description || row.task_type }}</div></template></el-table-column>
            <el-table-column label="负责人" width="130"><template #default="{ row }">{{ userName(row.assignee_id) }}</template></el-table-column>
            <el-table-column label="截止时间" width="180"><template #default="{ row }"><span :class="{ danger: row.is_overdue }">{{ formatDate(row.due_at) }}</span><el-tag v-if="row.is_overdue" size="small" type="danger">逾期</el-tag></template></el-table-column>
            <el-table-column label="提醒" width="170"><template #default="{ row }">{{ formatDate(row.remind_at) }}</template></el-table-column>
            <el-table-column label="状态" width="120"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : row.status === 'cancelled' ? 'info' : row.is_overdue ? 'danger' : 'warning'">{{ taskStatusLabel(row.status) }}</el-tag></template></el-table-column>
            <el-table-column v-if="canManage" label="操作" width="220"><template #default="{ row }"><el-button v-for="action in nextStatuses(row)" :key="action.value" text :type="action.value === 'completed' ? 'success' : action.value === 'cancelled' ? 'danger' : 'primary'" @click="changeTaskStatus(row, action.value)">{{ action.label }}</el-button><span v-if="!nextStatuses(row).length" class="muted">无可用操作</span></template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`文件 (${detail.files.length})`">
          <el-table :data="detail.files.flatMap((file) => file.versions)"><el-table-column prop="original_filename" label="文件名" min-width="240" /><el-table-column prop="version_no" label="版本" width="90" /><el-table-column prop="mime_type" label="类型" min-width="220" /><el-table-column prop="uploaded_at" label="上传时间" width="190"><template #default="{ row }">{{ formatDate(row.uploaded_at) }}</template></el-table-column></el-table>
        </el-tab-pane>

        <el-tab-pane :label="`操作历史 (${detail.operations.length})`">
          <el-timeline><el-timeline-item v-for="operation in detail.operations" :key="operation.id" :timestamp="formatDate(operation.created_at)"><strong>{{ actionLabel(operation.action) }}</strong><div class="muted">操作人：{{ userName(operation.user_id) }}</div></el-timeline-item></el-timeline>
        </el-tab-pane>
      </el-tabs>
    </template>

    <el-dialog v-model="partyDialog" title="关联合同主体" width="620px">
      <el-segmented v-model="partyMode" :options="[{ label: '选择已有主体', value: 'existing' }, { label: '创建新主体', value: 'new' }]" />
      <el-form label-position="top" class="dialog-form">
        <el-form-item label="合同角色"><el-select v-model="partyForm.role"><el-option label="甲方" value="party_a" /><el-option label="乙方" value="party_b" /><el-option label="其他" value="other" /></el-select></el-form-item>
        <el-form-item v-if="partyMode === 'existing'" label="主体"><el-select v-model="selectedPartyId" filterable><el-option v-for="party in parties" :key="party.id" :label="party.name" :value="party.id" /></el-select></el-form-item>
        <template v-else><el-form-item label="主体名称" required><el-input v-model="partyForm.name" /></el-form-item><el-form-item label="主体类型"><el-select v-model="partyForm.party_type"><el-option label="甲方" value="party_a" /><el-option label="乙方" value="party_b" /><el-option label="其他" value="other" /></el-select></el-form-item><el-form-item label="统一社会信用代码"><el-input v-model="partyForm.tax_no" /></el-form-item><div class="form-grid"><el-form-item label="电话"><el-input v-model="partyForm.phone" /></el-form-item><el-form-item label="邮箱"><el-input v-model="partyForm.email" /></el-form-item></div></template>
        <el-form-item label="备注"><el-input v-model="partyForm.notes" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="partyDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="savePartyLink">确认关联</el-button></template>
    </el-dialog>

    <el-dialog v-model="contactDialog" :title="`添加联系人 · ${selectedPartyForContact?.name || ''}`" width="560px"><el-form label-position="top"><div class="form-grid"><el-form-item label="姓名" required><el-input v-model="contactForm.name" /></el-form-item><el-form-item label="职务"><el-input v-model="contactForm.title" /></el-form-item><el-form-item label="电话"><el-input v-model="contactForm.phone" /></el-form-item><el-form-item label="邮箱"><el-input v-model="contactForm.email" /></el-form-item></div><el-form-item><el-checkbox v-model="contactForm.is_primary">设为主要联系人</el-checkbox></el-form-item></el-form><template #footer><el-button @click="contactDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveContact">保存</el-button></template></el-dialog>

    <el-dialog v-model="taskDialog" title="新建履约任务" width="660px"><el-form label-position="top"><el-form-item label="任务名称" required><el-input v-model="taskForm.title" /></el-form-item><el-form-item label="任务说明"><el-input v-model="taskForm.description" type="textarea" :rows="3" /></el-form-item><div class="form-grid"><el-form-item label="任务类型"><el-select v-model="taskForm.task_type"><el-option label="付款" value="payment" /><el-option label="交付" value="delivery" /><el-option label="验收" value="acceptance" /><el-option label="续签" value="renewal" /><el-option label="其他" value="other" /></el-select></el-form-item><el-form-item label="优先级"><el-select v-model="taskForm.priority"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item><el-form-item label="负责人"><el-select v-model="taskForm.assignee_id" clearable><el-option v-for="user in users" :key="user.id" :label="user.display_name" :value="user.id" /></el-select></el-form-item><el-form-item label="截止时间" required><el-date-picker v-model="taskForm.due_at" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" /></el-form-item><el-form-item label="提醒时间"><el-date-picker v-model="taskForm.remind_at" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" /></el-form-item></div></el-form><template #footer><el-button @click="taskDialog = false">取消</el-button><el-button type="primary" :icon="Check" :loading="saving" @click="saveTask">创建任务</el-button></template></el-dialog>
  </div>
</template>

<style scoped>
.detail-view { max-width: 1380px; min-height: 480px; margin: 0 auto; }
.detail-header, .pane-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.detail-header { margin-bottom: 16px; }
.detail-header h2 { margin: 8px 0 2px; }
.subtitle, .muted, .pane-toolbar span { color: #6b7280; font-size: 13px; }
.summary-band { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 18px; border: 1px solid #e5e7eb; border-radius: 6px; }
.summary-band div { display: flex; min-height: 76px; padding: 14px 18px; border-right: 1px solid #e5e7eb; flex-direction: column; justify-content: center; gap: 6px; }
.summary-band div:last-child { border-right: 0; }
.summary-band span { color: #6b7280; font-size: 13px; }
.summary-band strong { font-size: 18px; }
.pane-toolbar { margin-bottom: 14px; }
.danger { color: #dc2626; font-weight: 600; }
.dialog-form { margin-top: 18px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.analysis-toolbar { min-height: 40px; }
.run-select { width: min(520px, 100%); }
.analysis-meta { display: flex; flex-wrap: wrap; gap: 8px 24px; padding: 12px 16px; margin-bottom: 8px; color: #4b5563; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 13px; }
.analysis-result { padding: 24px 0; border-bottom: 1px solid #e5e7eb; }
.analysis-result:last-child { border-bottom: 0; }
.result-header, .result-actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.result-header h3 { margin: 0 0 4px; font-size: 18px; }
.result-actions { flex-wrap: wrap; justify-content: flex-end; }
.result-summary { padding: 12px 16px; margin: 16px 0; color: #374151; background: #f9fafb; border-left: 3px solid #2563eb; line-height: 1.7; }
.result-section { margin-top: 20px; }
.result-section h4 { margin: 0 0 10px; font-size: 15px; }
.result-section h4 span { margin-left: 4px; color: #6b7280; font-size: 12px; font-weight: 400; }
.field-value { margin: 0; white-space: pre-wrap; word-break: break-word; font: inherit; }
@media (max-width: 760px) { .summary-band { grid-template-columns: repeat(2, minmax(0, 1fr)); } .summary-band div { border-bottom: 1px solid #e5e7eb; } .form-grid { grid-template-columns: 1fr; } }
</style>
