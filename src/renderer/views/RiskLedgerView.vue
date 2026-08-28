<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, Edit, WarningFilled } from '@element-plus/icons-vue'
import { getRiskSummary, listFulfillmentAssignees, listRisks, updateRiskRemediation } from '../api'
import { useAuthStore } from '../stores/auth'
import type { FulfillmentAssignee, RiskLedgerItem, RiskSummary } from '../types'

const auth = useAuthStore()
const route = useRoute()
const loading = ref(false)
const saving = ref(false)
const risks = ref<RiskLedgerItem[]>([])
const assignees = ref<FulfillmentAssignee[]>([])
const summary = ref<RiskSummary>({ total: 0, open: 0, in_progress: 0, accepted: 0, mitigated: 0, dismissed: 0, closed: 0, overdue: 0, by_severity: [], by_status: [] })
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({ search: '', status: '', severity: '', contract_id: '', assignee_id: '', overdue_only: false, sort_by: 'remediation_due_at', sort_order: 'asc' as 'asc' | 'desc' })
const dialogVisible = ref(false)
const selectedRisk = ref<RiskLedgerItem | null>(null)
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

async function closeRisk(risk: RiskLedgerItem) {
  await ElMessageBox.confirm(`确认关闭“${risk.title}”？关闭后仍可由复核人员重新打开。`, '关闭风险', { type: 'warning' })
  selectedRisk.value = risk
  form.status = 'closed'
  form.assignee_id = risk.assignee_id || ''
  form.remediation_due_at = risk.remediation_due_at ? risk.remediation_due_at.slice(0, 16).replace('T', ' ') : ''
  form.remediation_notes = risk.remediation_notes || ''
  form.comment = ''
  dialogVisible.value = true
}

onMounted(async () => {
  filters.contract_id = typeof route.query.contract_id === 'string' ? route.query.contract_id : ''
  await Promise.all([load(), listFulfillmentAssignees().then((value) => { assignees.value = value })])
})
</script>

<template>
  <div v-loading="loading" class="risk-ledger">
    <div class="page-header">
      <div>
        <h2>风险台账</h2>
        <p>集中跟踪合同风险、整改负责人、期限和复核关闭状态。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
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
.page-header, .filters, .risk-context { display: flex; align-items: center; }
.page-header { justify-content: space-between; margin-bottom: 18px; }
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
@media (max-width: 760px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .summary-grid div { border-bottom: 1px solid #e5e7eb; } .summary-grid div:last-child { border-right: 1px solid #e5e7eb; } .filters .el-input, .filters .el-select { width: 100%; } .form-grid { grid-template-columns: 1fr; } }
</style>
