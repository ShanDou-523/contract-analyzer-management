<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Check, Refresh, Search, View } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import {
  getFulfillmentDashboard,
  listFulfillmentAssignees,
  listFulfillmentTasks,
  listNotifications,
  markAllNotificationsRead,
  scanFulfillmentReminders,
  updateFulfillmentTask,
  updateNotificationStatus,
} from '../api'
import type {
  FulfillmentAssignee,
  FulfillmentDashboard,
  FulfillmentNotification,
  FulfillmentTaskListItem,
  NotificationStatus,
  PagedFulfillmentTasks,
  PagedNotifications,
  TaskStatus,
} from '../types'

const router = useRouter()
const auth = useAuthStore()
const activeTab = ref('dashboard')
const loading = ref(false)
const scanning = ref(false)
const dashboard = ref<FulfillmentDashboard | null>(null)
const assignees = ref<FulfillmentAssignee[]>([])
const tasks = ref<PagedFulfillmentTasks>({ items: [], total: 0, page: 1, page_size: 20 })
const notifications = ref<PagedNotifications>({ items: [], total: 0, unread: 0, page: 1, page_size: 20 })
const taskFilters = reactive({
  search: '',
  status: '',
  priority: '',
  assignee_id: '',
  overdue_only: false,
})
const notificationFilters = reactive({ status: '' as NotificationStatus | '', notification_type: '' })

const canManage = computed(
  () => auth.user?.roles.some((role) => ['system_admin', 'org_admin', 'contract_manager'].includes(role)) || false,
)
const maxWorkload = computed(() => Math.max(1, ...(dashboard.value?.assignee_workloads.map((item) => item.open_count) || [1])))

async function loadDashboard() {
  dashboard.value = await getFulfillmentDashboard()
}

async function loadTasks(page = tasks.value.page) {
  tasks.value = await listFulfillmentTasks({
    page,
    page_size: tasks.value.page_size,
    search: taskFilters.search.trim() || undefined,
    status: taskFilters.status || undefined,
    priority: taskFilters.priority || undefined,
    assignee_id: taskFilters.assignee_id || undefined,
    overdue_only: taskFilters.overdue_only || undefined,
  })
}

async function loadNotifications(page = notifications.value.page) {
  notifications.value = await listNotifications({
    page,
    page_size: notifications.value.page_size,
    status: notificationFilters.status || undefined,
    notification_type: notificationFilters.notification_type || undefined,
  })
}

async function refreshAll() {
  loading.value = true
  try {
    await Promise.all([loadDashboard(), loadTasks(), loadNotifications()])
  } finally {
    loading.value = false
  }
}

async function scanReminders() {
  scanning.value = true
  try {
    const result = await scanFulfillmentReminders()
    ElMessage.success(`扫描完成，新增 ${result.created} 条通知`)
    await refreshAll()
  } finally {
    scanning.value = false
  }
}

async function changeTaskStatus(task: FulfillmentTaskListItem, status: TaskStatus) {
  await updateFulfillmentTask(task.contract_id, task.id, { status })
  await Promise.all([loadDashboard(), loadTasks()])
  ElMessage.success('任务状态已更新')
}

async function markNotification(notification: FulfillmentNotification, status: 'read' | 'ignored') {
  await updateNotificationStatus(notification.id, status)
  await Promise.all([loadDashboard(), loadNotifications()])
}

async function markAllRead() {
  const result = await markAllNotificationsRead()
  if (result.updated) ElMessage.success(`已将 ${result.updated} 条通知标记为已读`)
  await Promise.all([loadDashboard(), loadNotifications()])
}

function nextStatuses(task: FulfillmentTaskListItem): Array<{ label: string; value: TaskStatus }> {
  const transitions: Record<TaskStatus, Array<{ label: string; value: TaskStatus }>> = {
    pending: [{ label: '开始', value: 'in_progress' }, { label: '取消', value: 'cancelled' }],
    in_progress: [{ label: '完成', value: 'completed' }, { label: '退回', value: 'pending' }, { label: '取消', value: 'cancelled' }],
    completed: [],
    cancelled: [{ label: '重开', value: 'pending' }],
  }
  return transitions[task.status]
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

function taskStatusLabel(status: TaskStatus) {
  return { pending: '待处理', in_progress: '进行中', completed: '已完成', cancelled: '已取消' }[status]
}

function priorityLabel(priority: FulfillmentTaskListItem['priority']) {
  return { low: '低', medium: '中', high: '高', critical: '严重' }[priority]
}

function notificationStatusLabel(status: NotificationStatus) {
  return { unread: '未读', read: '已读', ignored: '已忽略' }[status]
}

function notificationRowClass({ row }: { row: FulfillmentNotification }) {
  return row.status === 'unread' ? 'notification-unread' : ''
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      loadDashboard(),
      loadTasks(1),
      loadNotifications(1),
      listFulfillmentAssignees().then((value) => { assignees.value = value }),
    ])
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-loading="loading" class="fulfillment-view">
    <header class="page-header">
      <div>
        <h2>履约看板</h2>
        <span class="muted">更新于 {{ formatDate(dashboard?.generated_at || null) }}</span>
      </div>
      <div class="header-actions">
        <el-button v-if="canManage" :icon="Bell" :loading="scanning" @click="scanReminders">扫描提醒</el-button>
        <el-button :icon="Refresh" @click="refreshAll">刷新</el-button>
      </div>
    </header>

    <section v-if="dashboard" class="summary-band">
      <div><span>未完成</span><strong>{{ dashboard.total_open }}</strong></div>
      <div><span>进行中</span><strong>{{ dashboard.in_progress }}</strong></div>
      <div><span>已逾期</span><strong :class="{ danger: dashboard.overdue }">{{ dashboard.overdue }}</strong></div>
      <div><span>今日到期</span><strong>{{ dashboard.due_today }}</strong></div>
      <div><span>未来 7 天</span><strong>{{ dashboard.due_next_7_days }}</strong></div>
      <div><span>未读通知</span><strong :class="{ accent: dashboard.unread_notifications }">{{ dashboard.unread_notifications }}</strong></div>
    </section>

    <el-tabs v-model="activeTab" class="workspace-tabs">
      <el-tab-pane label="看板概览" name="dashboard">
        <div v-if="dashboard" class="dashboard-grid">
          <section class="dashboard-section">
            <div class="section-heading"><h3>近期截止</h3><span>{{ dashboard.upcoming_tasks.length }} 项</span></div>
            <el-table :data="dashboard.upcoming_tasks" empty-text="暂无近期任务">
              <el-table-column label="任务" min-width="210">
                <template #default="{ row }"><strong>{{ row.title }}</strong><div class="muted">{{ row.contract_name }}</div></template>
              </el-table-column>
              <el-table-column label="负责人" width="130"><template #default="{ row }">{{ row.assignee_name || '未分配' }}</template></el-table-column>
              <el-table-column label="截止时间" width="180"><template #default="{ row }">{{ formatDate(row.due_at) }}</template></el-table-column>
              <el-table-column width="60"><template #default="{ row }"><el-button circle text :icon="View" title="查看合同" @click="router.push(`/contracts/${row.contract_id}`)" /></template></el-table-column>
            </el-table>
          </section>

          <section class="dashboard-section">
            <div class="section-heading"><h3>负责人负荷</h3><span>{{ dashboard.assignee_workloads.length }} 人</span></div>
            <div v-if="dashboard.assignee_workloads.length" class="workload-list">
              <div v-for="item in dashboard.assignee_workloads" :key="item.assignee_id || 'unassigned'" class="workload-row">
                <div class="workload-meta"><strong>{{ item.assignee_name }}</strong><span>{{ item.open_count }} 项<span v-if="item.overdue_count" class="danger"> · {{ item.overdue_count }} 项逾期</span></span></div>
                <el-progress :percentage="Math.round(item.open_count / maxWorkload * 100)" :show-text="false" :stroke-width="8" />
              </div>
            </div>
            <el-empty v-else description="暂无未完成任务" :image-size="72" />
            <div class="priority-strip">
              <div v-for="item in dashboard.priority_counts" :key="item.priority"><span>{{ priorityLabel(item.priority) }}</span><strong>{{ item.count }}</strong></div>
            </div>
          </section>
        </div>
      </el-tab-pane>

      <el-tab-pane :label="`任务查询 (${tasks.total})`" name="tasks">
        <div class="filter-bar">
          <el-input v-model="taskFilters.search" clearable placeholder="任务、合同名称或编号" :prefix-icon="Search" @keyup.enter="loadTasks(1)" />
          <el-select v-model="taskFilters.status" clearable placeholder="状态"><el-option label="待处理" value="pending" /><el-option label="进行中" value="in_progress" /><el-option label="已完成" value="completed" /><el-option label="已取消" value="cancelled" /></el-select>
          <el-select v-model="taskFilters.priority" clearable placeholder="优先级"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select>
          <el-select v-model="taskFilters.assignee_id" clearable filterable placeholder="负责人"><el-option label="未分配" value="unassigned" /><el-option v-for="user in assignees" :key="user.id" :label="user.display_name" :value="user.id" /></el-select>
          <el-checkbox v-model="taskFilters.overdue_only">仅逾期</el-checkbox>
          <el-button type="primary" :icon="Search" @click="loadTasks(1)">查询</el-button>
        </div>
        <el-table :data="tasks.items" stripe>
          <el-table-column label="任务" min-width="220"><template #default="{ row }"><strong>{{ row.title }}</strong><div class="muted">{{ row.task_type }}</div></template></el-table-column>
          <el-table-column label="合同" min-width="220"><template #default="{ row }"><el-link type="primary" @click="router.push(`/contracts/${row.contract_id}`)">{{ row.contract_name }}</el-link><div class="muted">{{ row.contract_no || '未设置编号' }}</div></template></el-table-column>
          <el-table-column label="负责人" width="130"><template #default="{ row }">{{ row.assignee_name || '未分配' }}</template></el-table-column>
          <el-table-column label="优先级" width="90"><template #default="{ row }"><el-tag :type="row.priority === 'critical' ? 'danger' : row.priority === 'high' ? 'warning' : 'info'">{{ priorityLabel(row.priority) }}</el-tag></template></el-table-column>
          <el-table-column label="截止时间" width="190"><template #default="{ row }"><span :class="{ danger: row.is_overdue }">{{ formatDate(row.due_at) }}</span></template></el-table-column>
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'completed' ? 'success' : row.status === 'cancelled' ? 'info' : row.is_overdue ? 'danger' : 'warning'">{{ taskStatusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column v-if="canManage" label="操作" width="190"><template #default="{ row }"><el-button v-for="action in nextStatuses(row)" :key="action.value" text size="small" :type="action.value === 'completed' ? 'success' : action.value === 'cancelled' ? 'danger' : 'primary'" @click="changeTaskStatus(row, action.value)">{{ action.label }}</el-button><span v-if="!nextStatuses(row).length" class="muted">-</span></template></el-table-column>
        </el-table>
        <el-pagination class="pagination" background layout="total, prev, pager, next" :total="tasks.total" :page-size="tasks.page_size" :current-page="tasks.page" @current-change="loadTasks" />
      </el-tab-pane>

      <el-tab-pane :label="`通知 (${notifications.unread})`" name="notifications">
        <div class="filter-bar notification-tools">
          <el-select v-model="notificationFilters.status" clearable placeholder="通知状态"><el-option label="未读" value="unread" /><el-option label="已读" value="read" /><el-option label="已忽略" value="ignored" /></el-select>
          <el-select v-model="notificationFilters.notification_type" clearable placeholder="通知类型"><el-option label="任务提醒" value="reminder" /><el-option label="任务逾期" value="overdue" /><el-option label="风险提醒" value="risk_reminder" /><el-option label="风险逾期" value="risk_overdue" /></el-select>
          <el-button :icon="Search" @click="loadNotifications(1)">筛选</el-button>
          <span class="toolbar-spacer" />
          <el-button :icon="Check" :disabled="!notifications.unread" @click="markAllRead">全部已读</el-button>
        </div>
        <el-table :data="notifications.items" :row-class-name="notificationRowClass" empty-text="暂无通知">
          <el-table-column label="通知" min-width="300"><template #default="{ row }"><strong>{{ row.title }}</strong><div class="notification-message">{{ row.message }}</div><el-tag v-if="row.risk_id" size="small" type="danger">风险整改</el-tag></template></el-table-column>
          <el-table-column label="合同" min-width="190"><template #default="{ row }"><el-link type="primary" @click="router.push(`/contracts/${row.contract_id}`)">{{ row.contract_name }}</el-link><div class="muted">{{ row.contract_no || '未设置编号' }}</div></template></el-table-column>
          <el-table-column label="触发时间" width="180"><template #default="{ row }">{{ formatDate(row.source_at) }}</template></el-table-column>
          <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag :type="row.status === 'unread' ? 'warning' : row.status === 'ignored' ? 'info' : 'success'">{{ notificationStatusLabel(row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="操作" width="150"><template #default="{ row }"><el-button v-if="row.status !== 'read'" text type="primary" @click="markNotification(row, 'read')">已读</el-button><el-button v-if="row.status !== 'ignored'" text type="info" @click="markNotification(row, 'ignored')">忽略</el-button></template></el-table-column>
        </el-table>
        <el-pagination class="pagination" background layout="total, prev, pager, next" :total="notifications.total" :page-size="notifications.page_size" :current-page="notifications.page" @current-change="loadNotifications" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.fulfillment-view { max-width: 1440px; min-height: 520px; margin: 0 auto; }
.page-header, .header-actions, .section-heading, .filter-bar, .workload-meta, .priority-strip { display: flex; align-items: center; }
.page-header { justify-content: space-between; gap: 20px; margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; }
.header-actions, .filter-bar { gap: 10px; }
.muted, .section-heading span, .workload-meta span, .notification-message { color: #6b7280; font-size: 13px; }
.summary-band { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); margin-bottom: 18px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.summary-band div { display: flex; min-height: 76px; padding: 14px 18px; border-right: 1px solid #e5e7eb; flex-direction: column; justify-content: center; gap: 6px; }
.summary-band div:last-child { border-right: 0; }
.summary-band span { color: #6b7280; font-size: 13px; }
.summary-band strong { font-size: 20px; }
.workspace-tabs { min-height: 390px; padding: 0 18px 18px; border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.dashboard-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(320px, .75fr); gap: 28px; }
.dashboard-section { min-width: 0; }
.section-heading { justify-content: space-between; min-height: 46px; border-bottom: 1px solid #ebeef5; }
.section-heading h3 { font-size: 16px; }
.workload-list { padding: 8px 0 2px; }
.workload-row { padding: 10px 0; }
.workload-meta { justify-content: space-between; margin-bottom: 7px; }
.priority-strip { justify-content: space-between; margin-top: 18px; padding-top: 14px; border-top: 1px solid #ebeef5; }
.priority-strip div { display: flex; flex-direction: column; gap: 4px; color: #6b7280; font-size: 12px; }
.priority-strip strong { color: #303133; font-size: 17px; }
.filter-bar { margin-bottom: 14px; flex-wrap: wrap; }
.filter-bar .el-input { width: 270px; }
.filter-bar .el-select { width: 145px; }
.notification-tools .toolbar-spacer { flex: 1; }
.notification-message { margin-top: 4px; line-height: 1.45; }
.danger { color: #dc2626; font-weight: 600; }
.accent { color: #2563eb; }
.pagination { justify-content: flex-end; margin-top: 16px; }
:deep(.notification-unread > td.el-table__cell) { background: #fff8e8; }
@media (max-width: 980px) { .summary-band { grid-template-columns: repeat(3, minmax(0, 1fr)); } .summary-band div:nth-child(3) { border-right: 0; } .dashboard-grid { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .page-header { align-items: stretch; flex-direction: column; } .header-actions { flex-wrap: wrap; } .summary-band { grid-template-columns: repeat(2, minmax(0, 1fr)); } .summary-band div:nth-child(3) { border-right: 1px solid #e5e7eb; } .summary-band div:nth-child(2n) { border-right: 0; } .filter-bar .el-input, .filter-bar .el-select { width: 100%; } .notification-tools .toolbar-spacer { display: none; } }
</style>
