<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Search, Edit, WarningFilled, Bell, Download, Camera, Promotion, RefreshRight } from '@element-plus/icons-vue'
import { downloadRiskReport, downloadRiskReportSnapshots, getRiskReportOverview, getRiskSummary, listBackgroundJobs, listFulfillmentAssignees, listNotificationDeliveries, listRiskReportSnapshots, listRisks, queueNotificationDispatch, queueRiskReportSnapshot, retryBackgroundJob, scanRiskReminders, updateRiskRemediation } from '../api'
import { useAuthStore } from '../stores/auth'
import type { BackgroundJob, FulfillmentAssignee, PagedBackgroundJobs, PagedNotificationDeliveries, PagedRiskReportSnapshots, RiskLedgerItem, RiskReportOverview, RiskSummary } from '../types'

const auth = useAuthStore()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const scanning = ref(false)
const reportLoading = ref(false)
const operationsLoading = ref(false)
const snapshotting = ref(false)
const dispatching = ref(false)
const risks = ref<RiskLedgerItem[]>([])
const assignees = ref<FulfillmentAssignee[]>([])
const summary = ref<RiskSummary>({ total: 0, open: 0, in_progress: 0, accepted: 0, mitigated: 0, dismissed: 0, closed: 0, overdue: 0, by_severity: [], by_status: [] })
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ search: '', status: '', severity: '', contract_id: '', assignee_id: '', overdue_only: false, sort_by: 'remediation_due_at', sort_order: 'asc' as 'asc' | 'desc' })
const dialogVisible = ref(false)
const selectedRisk = ref<RiskLedgerItem | null>(null)
const report = ref<RiskReportOverview | null>(null)
const operationsTab = ref('snapshots')
const snapshotPage = ref(1)
const jobPage = ref(1)
const deliveryPage = ref(1)
const snapshots = ref<PagedRiskReportSnapshots>({ items: [], total: 0, page: 1, page_size: 30 })
const jobs = ref<PagedBackgroundJobs>({ items: [], total: 0, page: 1, page_size: 20 })
const deliveries = ref<PagedNotificationDeliveries>({ items: [], total: 0, page: 1, page_size: 20 })
const form = reactive({ status: '', assignee_id: '', remediation_due_at: '', remediation_notes: '', comment: '' })

const canManage = computed(() => auth.user?.roles.some((role) => ['system_admin', 'org_admin', 'contract_manager', 'reviewer'].includes(role)) || false)
const canClose = computed(() => auth.user?.roles.some((role) => ['system_admin', 'org_admin', 'reviewer'].includes(role)) || false)

const statusOptions = [
  { value: 'open', label: '待处置' },
  { value: 'in_progress', label: '整改中' },
  { value: 'accepted', label: '接受风险' },
  { value: 'mitigated', label: '已缓释' },
  { value: 'dismissed', label: '已排除' },
  { value: 'closed', label: '已关闭' },
]
const severityOptions = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'critical', label: '严重' },
]

function statusLabel(status: string) { return statusOptions.find((item) => item.value === status)?.label || status }
function severityLabel(severity: string) { return severityOptions.find((item) => item.value === severity)?.label || severity }
function statusType(status: string) { return status === 'closed' || status === 'mitigated' ? 'success' : status === 'dismissed' || status === 'accepted' ? 'info' : status === 'in_progress' ? 'warning' : 'danger' }
function severityType(severity: string) { return severity === 'critical' || severity === 'high' ? 'danger' : severity === 'medium' ? 'warning' : 'info' }
function formatDate(value: string | null) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-' }
function jobStatusLabel(status: string) { return { queued: '排队中', running: '执行中', succeeded: '已完成', failed: '失败', cancelled: '已取消' }[status] || status }
function jobStatusType(status: string) { return status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : status === 'running' ? 'warning' : 'info' }
function deliveryStatusLabel(status: string) { return { queued: '待投递', delivering: '投递中', sent: '已发送', failed: '失败' }[status] || status }
function jobTypeLabel(type: string) { return { risk_reminder_scan: '风险提醒扫描', notification_dispatch: '通知投递调度', notification_delivery: '通知投递', risk_report_snapshot: '风险日报快照' }[type] || type }

async function load() {
  loading.value = true
  try {
    const [paged, totals] = await Promise.all([
      listRisks({ ...filters, page: page.value, page_size: pageSize.value }),
      getRiskSummary(),
    ])
    risks.value = paged.items
    total.value = paged.total
    summary.value = totals
  } finally {
    loading.value = false
  }
}

async function loadReport() {
  reportLoading.value = true
  try {
    report.value = await getRiskReportOverview(30)
  } finally {
    reportLoading.value = false
  }
}

async function loadOperations() {
  operationsLoading.value = true
  try {
    const [snapshotResult, jobResult, deliveryResult] = await Promise.all([
      listRiskReportSnapshots({ page: snapshotPage.value, page_size: 30 }),
      listBackgroundJobs({ page: jobPage.value, page_size: 20 }),
      listNotificationDeliveries({ page: deliveryPage.value, page_size: 20 }),
    ])
    snapshots.value = snapshotResult
    jobs.value = jobResult
    deliveries.value = deliveryResult
  } finally {
    operationsLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([load(), loadReport(), loadOperations()])
}

async function scanReminders() {
  scanning.value = true
  try {
    await scanRiskReminders()
    ElMessage.success('风险提醒扫描已排队')
    await loadOperations()
  } finally {
    scanning.value = false
  }
}

async function createSnapshot() {
  snapshotting.value = true
  try {
    await queueRiskReportSnapshot()
    ElMessage.success('风险日报快照已排队')
    await loadOperations()
  } finally {
    snapshotting.value = false
  }
}

async function dispatchNotifications() {
  dispatching.value = true
  try {
    await queueNotificationDispatch()
    ElMessage.success('通知投递调度已排队')
    await loadOperations()
  } finally {
    dispatching.value = false
  }
}

async function retryJob(job: BackgroundJob) {
  await retryBackgroundJob(job.id)
  ElMessage.success('失败任务已重新排队')
  await loadOperations()
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

async function exportReport() {
  const blob = await downloadRiskReport(30)
  saveBlob(blob, `risk-report-${new Date().toISOString().slice(0, 10)}.csv`)
}

async function exportSnapshotHistory() {
  const blob = await downloadRiskReportSnapshots()
  saveBlob(blob, `risk-snapshots-${new Date().toISOString().slice(0, 10)}.csv`)
}

function applyFilters() { page.value = 1; load() }
function openEdit(risk: RiskLedgerItem) {
  selectedRisk.value = risk
  form.status = risk.status
  form.assignee_id = risk.assignee_id || ''
  form.remediation_due_at = risk.remediation_due_at ? risk.remediation_due_at.slice(0, 16).replace('T', ' ') : ''
  form.remediation_notes = risk.remediation_notes || ''
  form.comment = ''
  dialogVisible.value = true
}

async function save() {
  if (!selectedRisk.value) return
  if (form.status === 'closed' && !canClose.value) {
    ElMessage.warning('只有复核人员可以关闭风险')
    return
  }
  if (['accepted', 'mitigated', 'dismissed', 'closed'].includes(form.status) && !form.comment.trim()) {
    ElMessage.warning('完成或关闭风险整改必须填写复核意见')
    return
  }
  saving.value = true
  try {
    await updateRiskRemediation(selectedRisk.value.id, {
      status: form.status,
      assignee_id: form.assignee_id || null,
      remediation_due_at: form.remediation_due_at || null,
      remediation_notes: form.remediation_notes || null,
      comment: form.comment,
    })
    dialogVisible.value = false
    ElMessage.success('风险整改已更新')
    await load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  filters.contract_id = typeof route.query.contract_id === 'string' ? route.query.contract_id : ''
  await Promise.all([load(), loadReport(), loadOperations(), listFulfillmentAssignees().then((value) => { assignees.value = value })])
})
</script>

<template>
  <div v-loading="loading" class="risk-ledger">
    <div class="page-header">
      <div>
        <h2>风险台账</h2>
        <p>集中跟踪合同风险、整改负责人、期限和复核关闭状态。</p>
      </div>
      <div class="header-actions">
        <el-button v-if="canManage" :icon="Bell" :loading="scanning" @click="scanReminders">扫描提醒</el-button>
        <el-button :icon="Download" @click="exportReport">导出报表</el-button>
        <el-button :icon="Refresh" :loading="loading" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <section class="summary-grid">
      <div><span>风险总数</span><strong>{{ summary.total }}</strong></div>
      <div><span>待处置</span><strong class="danger">{{ summary.open }}</strong></div>
      <div><span>整改中</span><strong class="warning">{{ summary.in_progress }}</strong></div>
      <div><span>逾期整改</span><strong class="danger">{{ summary.overdue }}</strong></div>
      <div><span>已关闭</span><strong class="success">{{ summary.closed }}</strong></div>
    </section>

    <el-card shadow="never">
      <div class="filters">
        <el-input v-model="filters.search" clearable placeholder="搜索风险或合同" :prefix-icon="Search" @keyup.enter="applyFilters" />
        <el-select v-model="filters.status" clearable placeholder="全部状态" @change="applyFilters"><el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
        <el-select v-model="filters.severity" clearable placeholder="全部等级" @change="applyFilters"><el-option v-for="item in severityOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select>
        <el-select v-model="filters.assignee_id" clearable placeholder="全部负责人" @change="applyFilters"><el-option v-for="item in assignees" :key="item.id" :label="item.display_name" :value="item.id" /></el-select>
        <el-checkbox v-model="filters.overdue_only" @change="applyFilters">只看逾期</el-checkbox>
        <el-button type="primary" :icon="Search" @click="applyFilters">查询</el-button>
      </div>

      <el-table :data="risks" stripe empty-text="暂无风险项">
        <el-table-column label="风险项" min-width="280"><template #default="{ row }"><strong>{{ row.title }}</strong><div class="muted">{{ row.description || '-' }}</div><el-tag v-if="row.is_overdue" type="danger" size="small"><el-icon><WarningFilled /></el-icon>逾期</el-tag></template></el-table-column>
        <el-table-column label="合同" min-width="210"><template #default="{ row }"><el-link type="primary" @click="$router.push(`/contracts/${row.contract_id}`)">{{ row.contract_name }}</el-link><div class="muted">{{ row.contract_no || '未设置编号' }}</div></template></el-table-column>
        <el-table-column label="等级" width="90"><template #default="{ row }"><el-tag :type="severityType(row.severity)">{{ severityLabel(row.severity) }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="105"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
        <el-table-column label="负责人" width="120"><template #default="{ row }">{{ row.assignee_name || '未分配' }}</template></el-table-column>
        <el-table-column label="整改期限" width="170"><template #default="{ row }"><span :class="{ danger: row.is_overdue }">{{ formatDate(row.remediation_due_at) }}</span></template></el-table-column>
        <el-table-column label="操作" width="120" fixed="right"><template #default="{ row }"><el-button v-if="canManage" text type="primary" :icon="Edit" @click="openEdit(row)">整改</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" class="pagination" layout="total, sizes, prev, pager, next" :page-sizes="[20, 50, 100]" :total="total" @current-change="load" />
    </el-card>

    <section v-loading="reportLoading" class="report-section">
      <div class="report-heading"><div><h3>组织风险报表</h3><span class="muted">近 30 天风险创建趋势、合同风险排序和整改负荷。</span></div><el-button text :icon="Refresh" @click="loadReport">更新报表</el-button></div>
      <div v-if="report" class="report-grid">
        <div class="report-panel">
          <div class="section-title">风险趋势</div>
          <el-table :data="report.trend.slice(-14)" size="small" empty-text="暂无趋势数据">
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="total" label="新增" width="72" />
            <el-table-column prop="open" label="待处置" width="82" />
            <el-table-column prop="overdue" label="逾期" width="72" />
            <el-table-column prop="closed" label="已关闭" width="82" />
          </el-table>
        </div>
        <div class="report-panel">
          <div class="section-title">合同风险排行</div>
          <el-table :data="report.contract_rankings.slice(0, 8)" size="small" empty-text="暂无合同风险">
            <el-table-column label="合同" min-width="180"><template #default="{ row }"><el-link type="primary" @click="$router.push(`/contracts/${row.contract_id}`)">{{ row.contract_name }}</el-link><div class="muted">{{ row.contract_no || '未设置编号' }}</div></template></el-table-column>
            <el-table-column prop="total" label="总数" width="62" />
            <el-table-column prop="open" label="待处置" width="72" />
            <el-table-column prop="overdue" label="逾期" width="62" />
          </el-table>
        </div>
        <div class="report-panel report-panel-wide">
          <div class="section-title">整改负责人负荷</div>
          <el-table :data="report.assignee_workloads" size="small" empty-text="暂无整改负责人">
            <el-table-column prop="assignee_name" label="负责人" min-width="150" />
            <el-table-column prop="total" label="风险总数" width="90" />
            <el-table-column prop="open" label="待处置" width="90" />
            <el-table-column prop="overdue" label="逾期" width="80" />
            <el-table-column prop="closed" label="已关闭" width="90" />
          </el-table>
        </div>
      </div>
    </section>

    <section v-loading="operationsLoading" class="operations-section">
      <div class="report-heading"><div><h3>自动化与历史</h3></div><el-button text :icon="Refresh" @click="loadOperations">刷新</el-button></div>
      <el-tabs v-model="operationsTab">
        <el-tab-pane :label="`日报快照 (${snapshots.total})`" name="snapshots">
          <div class="operations-toolbar">
            <el-button v-if="canManage" type="primary" :icon="Camera" :loading="snapshotting" @click="createSnapshot">生成今日快照</el-button>
            <el-button :icon="Download" @click="exportSnapshotHistory">导出历史</el-button>
          </div>
          <el-table :data="snapshots.items" stripe empty-text="暂无日报快照">
            <el-table-column prop="snapshot_date" label="日期" width="120" />
            <el-table-column prop="total" label="风险总数" width="90" />
            <el-table-column prop="active" label="待处置" width="90" />
            <el-table-column prop="overdue" label="逾期" width="80" />
            <el-table-column label="逾期率" width="90"><template #default="{ row }"><span :class="{ danger: row.overdue_rate > 0 }">{{ row.overdue_rate.toFixed(1) }}%</span></template></el-table-column>
            <el-table-column prop="critical" label="严重风险" width="90" />
            <el-table-column prop="closed" label="已关闭" width="90" />
            <el-table-column label="生成时间" min-width="170"><template #default="{ row }">{{ formatDate(row.generated_at) }}</template></el-table-column>
          </el-table>
          <el-pagination v-model:current-page="snapshotPage" class="pagination" layout="total, prev, pager, next" :page-size="30" :total="snapshots.total" @current-change="loadOperations" />
        </el-tab-pane>

        <el-tab-pane :label="`后台任务 (${jobs.total})`" name="jobs">
          <el-table :data="jobs.items" stripe empty-text="暂无后台任务">
            <el-table-column label="任务" min-width="190"><template #default="{ row }"><strong>{{ jobTypeLabel(row.job_type) }}</strong><div class="muted mono">{{ row.id }}</div></template></el-table-column>
            <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="jobStatusType(row.status)">{{ jobStatusLabel(row.status) }}</el-tag></template></el-table-column>
            <el-table-column label="尝试" width="80"><template #default="{ row }">{{ row.attempts }}/{{ row.max_attempts }}</template></el-table-column>
            <el-table-column label="错误" min-width="220"><template #default="{ row }"><span v-if="row.error_message" class="danger">{{ row.error_message }}</span><span v-else class="muted">-</span></template></el-table-column>
            <el-table-column label="创建时间" width="170"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
            <el-table-column v-if="canManage" label="操作" width="90" fixed="right"><template #default="{ row }"><el-button v-if="row.status === 'failed'" text type="primary" :icon="RefreshRight" @click="retryJob(row)">重试</el-button></template></el-table-column>
          </el-table>
          <el-pagination v-model:current-page="jobPage" class="pagination" layout="total, prev, pager, next" :page-size="20" :total="jobs.total" @current-change="loadOperations" />
        </el-tab-pane>

        <el-tab-pane :label="`通知投递 (${deliveries.total})`" name="deliveries">
          <div class="operations-toolbar"><el-button v-if="canManage" type="primary" :icon="Promotion" :loading="dispatching" @click="dispatchNotifications">调度待投递通知</el-button></div>
          <el-table :data="deliveries.items" stripe empty-text="暂无通知投递记录">
            <el-table-column label="通知" min-width="260"><template #default="{ row }"><strong>{{ row.notification_title }}</strong><div class="muted">{{ row.recipient_name }}</div></template></el-table-column>
            <el-table-column prop="provider_name" label="Provider" width="100" />
            <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="jobStatusType(row.status === 'sent' ? 'succeeded' : row.status === 'delivering' ? 'running' : row.status)">{{ deliveryStatusLabel(row.status) }}</el-tag></template></el-table-column>
            <el-table-column label="尝试" width="80"><template #default="{ row }">{{ row.attempt_count }}/{{ row.max_attempts }}</template></el-table-column>
            <el-table-column label="Provider 消息 ID" min-width="190"><template #default="{ row }"><span class="mono">{{ row.provider_message_id || '-' }}</span></template></el-table-column>
            <el-table-column label="错误" min-width="210"><template #default="{ row }"><span :class="{ danger: row.last_error }">{{ row.last_error || '-' }}</span></template></el-table-column>
            <el-table-column label="更新时间" width="170"><template #default="{ row }">{{ formatDate(row.updated_at) }}</template></el-table-column>
          </el-table>
          <el-pagination v-model:current-page="deliveryPage" class="pagination" layout="total, prev, pager, next" :page-size="20" :total="deliveries.total" @current-change="loadOperations" />
        </el-tab-pane>
      </el-tabs>
    </section>

    <el-dialog v-model="dialogVisible" title="风险整改" width="620px">
      <template v-if="selectedRisk">
        <div class="risk-context"><strong>{{ selectedRisk.title }}</strong><span>{{ selectedRisk.contract_name }}</span></div>
        <el-form label-position="top">
          <div class="form-grid">
            <el-form-item label="状态"><el-select v-model="form.status"><el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" :disabled="item.value === 'closed' && !canClose" /></el-select></el-form-item>
            <el-form-item label="负责人"><el-select v-model="form.assignee_id" clearable><el-option v-for="item in assignees" :key="item.id" :label="item.display_name" :value="item.id" /></el-select></el-form-item>
          </div>
          <el-form-item label="整改期限"><el-date-picker v-model="form.remediation_due_at" type="datetime" value-format="YYYY-MM-DD HH:mm" placeholder="选择整改期限" /></el-form-item>
          <el-form-item label="整改说明"><el-input v-model="form.remediation_notes" type="textarea" :rows="4" placeholder="记录整改方案、处理进展或业务依据" /></el-form-item>
          <el-form-item :label="['accepted', 'mitigated', 'dismissed', 'closed'].includes(form.status) ? '复核意见（必填）' : '本次更新说明'"><el-input v-model="form.comment" type="textarea" :rows="3" placeholder="填写本次状态变更的依据" /></el-form-item>
        </el-form>
      </template>
      <template #footer><el-button @click="dialogVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存整改</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.risk-ledger { max-width: 1400px; margin: 0 auto; }
.page-header, .filters, .risk-context, .header-actions, .report-heading { display: flex; align-items: center; }
.page-header { justify-content: space-between; margin-bottom: 18px; }
.header-actions { gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.page-header h2 { margin: 0 0 6px; }
.page-header p, .muted { margin: 0; color: #6b7280; font-size: 13px; }
.summary-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 18px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.summary-grid div { display: flex; min-height: 76px; padding: 14px 18px; border-right: 1px solid #e5e7eb; flex-direction: column; justify-content: center; gap: 6px; }
.summary-grid div:last-child { border-right: 0; }
.summary-grid span { color: #6b7280; font-size: 13px; }
.summary-grid strong { font-size: 20px; }
.danger { color: #dc2626; font-weight: 600; }
.warning { color: #d97706; font-weight: 600; }
.success { color: #16a34a; font-weight: 600; }
.filters { gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.filters .el-input { width: 260px; }
.filters .el-select { width: 150px; }
.risk-context { justify-content: space-between; padding: 12px 16px; margin-bottom: 18px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; }
.risk-context span { color: #6b7280; font-size: 13px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px; }
.pagination { justify-content: flex-end; margin-top: 18px; }
.report-section { margin-top: 18px; padding: 18px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.operations-section { margin-top: 18px; padding: 18px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.report-heading { justify-content: space-between; margin-bottom: 14px; }
.report-heading h3 { margin: 0 0 4px; }
.report-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; }
.report-panel { min-width: 0; }
.report-panel-wide { grid-column: 1 / -1; }
.section-title { margin-bottom: 8px; font-weight: 600; color: #303133; }
.operations-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.mono { font-family: Consolas, 'Courier New', monospace; font-size: 12px; }
@media (max-width: 760px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .summary-grid div { border-bottom: 1px solid #e5e7eb; } .summary-grid div:last-child { border-right: 1px solid #e5e7eb; } .filters .el-input, .filters .el-select { width: 100%; } .form-grid { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .report-grid { grid-template-columns: 1fr; } .report-panel-wide { grid-column: auto; } }
</style>
