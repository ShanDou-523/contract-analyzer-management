<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, FolderOpened, Plus, Refresh, Upload } from '@element-plus/icons-vue'
import {
  confirmContractImport,
  createContract,
  createContractImport,
  deleteContract,
  getContractFileBlob,
  listContractFiles,
  listContracts,
  listRecycleBin,
  restoreContract,
  uploadContractFile,
  validateContractImport,
} from '../api'
import type { Contract, ContractFile, ContractImportPreview, FileVersion } from '../types'

const contracts = ref<Contract[]>([])
const total = ref(0)
const loading = ref(false)
const mode = ref<'active' | 'recycle'>('active')
const search = ref('')
const status = ref('')
const page = ref(1)
const pageSize = ref(20)
const sortBy = ref('updated_at')
const sortOrder = ref<'asc' | 'desc'>('desc')
const createVisible = ref(false)
const saving = ref(false)
const createForm = reactive({
  contract_no: '',
  name: '',
  category: '',
  party_a_name: '',
  party_b_name: '',
  project_name: '',
  department_name: '',
  status: 'draft',
  risk_level: 'medium',
  amount: '',
  currency: 'CNY',
})
const selectedContract = ref<Contract | null>(null)
const filesVisible = ref(false)
const filesLoading = ref(false)
const contractFiles = ref<ContractFile[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const uploadingFile = ref(false)
const importVisible = ref(false)
const importInput = ref<HTMLInputElement | null>(null)
const importLoading = ref(false)
const importStep = ref(0)
const importPreview = ref<ContractImportPreview | null>(null)

async function loadContracts() {
  loading.value = true
  try {
    const result = mode.value === 'active'
      ? await listContracts({ page: page.value, page_size: pageSize.value, search: search.value || undefined, status: status.value || undefined, sort_by: sortBy.value, sort_order: sortOrder.value })
      : await listRecycleBin({ page: page.value, page_size: pageSize.value, search: search.value || undefined, sort_by: sortBy.value === 'deleted_at' ? 'deleted_at' : sortBy.value, sort_order: sortOrder.value })
    contracts.value = result.items
    total.value = result.total
  } finally {
    loading.value = false
  }
}

function applySearch() {
  page.value = 1
  loadContracts()
}

function resetCreateForm() {
  Object.assign(createForm, {
    contract_no: '', name: '', category: '', party_a_name: '', party_b_name: '', project_name: '',
    department_name: '', status: 'draft', risk_level: 'medium', amount: '', currency: 'CNY',
  })
}

async function saveContract() {
  if (!createForm.name.trim()) {
    ElMessage.warning('请填写合同名称')
    return
  }
  saving.value = true
  try {
    await createContract({
      ...createForm,
      contract_no: createForm.contract_no || undefined,
      category: createForm.category || undefined,
      party_a_name: createForm.party_a_name || undefined,
      party_b_name: createForm.party_b_name || undefined,
      project_name: createForm.project_name || undefined,
      department_name: createForm.department_name || undefined,
      amount: createForm.amount || undefined,
    })
    createVisible.value = false
    resetCreateForm()
    await loadContracts()
    ElMessage.success('合同已创建')
  } finally {
    saving.value = false
  }
}

async function moveToRecycle(contract: Contract) {
  await deleteContract(contract.id)
  await loadContracts()
  ElMessage.success('合同已移入回收站')
}

async function restore(contract: Contract) {
  await restoreContract(contract.id)
  await loadContracts()
  ElMessage.success('合同已恢复')
}

async function openFiles(contract: Contract) {
  selectedContract.value = contract
  filesVisible.value = true
  filesLoading.value = true
  try {
    contractFiles.value = await listContractFiles(contract.id)
  } finally {
    filesLoading.value = false
  }
}

function chooseFile() {
  fileInput.value?.click()
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !selectedContract.value) return
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!['.pdf', '.docx', '.xlsx', '.csv'].includes(extension)) {
    ElMessage.error('文件版本仅支持 PDF、DOCX、XLSX、CSV')
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小超过50MB限制')
    return
  }
  uploadingFile.value = true
  try {
    await uploadContractFile(selectedContract.value.id, file)
    contractFiles.value = await listContractFiles(selectedContract.value.id)
    ElMessage.success('文件版本已上传')
  } finally {
    uploadingFile.value = false
  }
}

async function openVersion(version: FileVersion, inline: boolean) {
  const blob = await getContractFileBlob(inline ? version.preview_url : version.download_url)
  const url = URL.createObjectURL(blob)
  if (inline) {
    window.open(url, '_blank', 'noopener,noreferrer')
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    return
  }
  const link = document.createElement('a')
  link.href = url
  link.download = version.original_filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function openImport() {
  importVisible.value = true
  importStep.value = 0
  importPreview.value = null
}

function chooseImportFile() {
  importInput.value?.click()
}

async function onImportSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!['.xlsx', '.csv'].includes(extension)) {
    ElMessage.error('导入仅支持 XLSX 或 CSV')
    return
  }
  importLoading.value = true
  try {
    importPreview.value = await createContractImport(file)
    importStep.value = 1
  } finally {
    importLoading.value = false
  }
}

async function validateImport() {
  if (!importPreview.value) return
  importLoading.value = true
  try {
    importPreview.value = await validateContractImport(importPreview.value.id)
    importStep.value = 2
  } finally {
    importLoading.value = false
  }
}

async function confirmImport() {
  if (!importPreview.value) return
  importLoading.value = true
  try {
    const result = await confirmContractImport(importPreview.value.id)
    importStep.value = 3
    await loadContracts()
    ElMessage.success(`已导入 ${result.created_count} 份合同`)
  } finally {
    importLoading.value = false
  }
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '-'
}

function formatAmount(value: string | number | null, currency: string) {
  return value === null || value === undefined || value === '' ? '-' : `${value} ${currency}`
}

function formatSize(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

watch([mode, pageSize], () => {
  page.value = 1
  if (mode.value === 'recycle') sortBy.value = 'deleted_at'
  else if (sortBy.value === 'deleted_at') sortBy.value = 'updated_at'
  loadContracts()
})

onMounted(loadContracts)
</script>

<template>
  <div class="contracts-view">
    <div class="ledger-header">
      <div>
        <el-button text :icon="ArrowLeft" @click="$router.back()">返回</el-button>
        <h2>合同台账</h2>
        <p>管理合同主数据、文件版本和批量导入；旧版文档分析入口仍保留在首页。</p>
      </div>
      <div class="ledger-actions">
        <el-button :icon="Refresh" :loading="loading" @click="loadContracts">刷新</el-button>
        <el-button :icon="Upload" @click="openImport">导入 XLSX / CSV</el-button>
        <el-button v-if="mode === 'active'" type="primary" :icon="Plus" @click="createVisible = true">新建合同</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="filters">
        <el-segmented v-model="mode" :options="[{ label: '在册合同', value: 'active' }, { label: '回收站', value: 'recycle' }]" />
        <el-input v-model="search" clearable placeholder="搜索编号、名称或合同主体" @keyup.enter="applySearch" />
        <el-select v-if="mode === 'active'" v-model="status" clearable placeholder="全部状态" @change="page = 1; loadContracts">
          <el-option label="草稿" value="draft" /><el-option label="生效中" value="active" />
          <el-option label="已到期" value="expired" /><el-option label="已终止" value="terminated" />
        </el-select>
        <el-select v-model="sortBy" placeholder="排序字段" @change="loadContracts">
          <el-option label="更新时间" value="updated_at" /><el-option label="创建时间" value="created_at" />
          <el-option label="合同名称" value="name" /><el-option label="合同编号" value="contract_no" />
          <el-option v-if="mode === 'active'" label="金额" value="amount" /><el-option v-if="mode === 'recycle'" label="删除时间" value="deleted_at" />
        </el-select>
        <el-button text @click="sortOrder = sortOrder === 'desc' ? 'asc' : 'desc'; loadContracts">{{ sortOrder === 'desc' ? '降序' : '升序' }}</el-button>
      </div>

      <el-table v-loading="loading" :data="contracts" stripe>
        <el-table-column prop="contract_no" label="合同编号" min-width="150" />
        <el-table-column prop="name" label="合同名称" min-width="220" />
        <el-table-column prop="category" label="类别" width="120" />
        <el-table-column label="合同主体" min-width="220">
          <template #default="{ row }">{{ row.party_a_name || '-' }} / {{ row.party_b_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="金额" width="150"><template #default="{ row }">{{ formatAmount(row.amount, row.currency) }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : row.status === 'terminated' ? 'danger' : 'info'">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column label="风险" width="90"><template #default="{ row }"><el-tag :type="row.risk_level === 'critical' || row.risk_level === 'high' ? 'danger' : 'warning'">{{ row.risk_level }}</el-tag></template></el-table-column>
        <el-table-column :label="mode === 'recycle' ? '删除时间' : '更新时间'" width="125"><template #default="{ row }">{{ formatDate(mode === 'recycle' ? row.deleted_at : row.updated_at) }}</template></el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <template v-if="mode === 'active'">
              <el-button text type="primary" @click="$router.push(`/contracts/${row.id}`)">详情</el-button>
              <el-button text type="primary" :icon="FolderOpened" @click="openFiles(row)">文件</el-button>
              <el-button text type="danger" @click="moveToRecycle(row)">移入回收站</el-button>
            </template>
            <el-button v-else text type="primary" @click="restore(row)">恢复</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" class="pagination" layout="total, sizes, prev, pager, next" :total="total" :page-sizes="[20, 50, 100]" @current-change="loadContracts" />
    </el-card>

    <el-dialog v-model="createVisible" title="新建合同" width="680px" @closed="resetCreateForm">
      <el-form :model="createForm" label-position="top">
        <div class="form-grid">
          <el-form-item label="合同名称" required><el-input v-model="createForm.name" /></el-form-item>
          <el-form-item label="合同编号"><el-input v-model="createForm.contract_no" /></el-form-item>
          <el-form-item label="类别"><el-input v-model="createForm.category" /></el-form-item>
          <el-form-item label="金额"><el-input v-model="createForm.amount" /></el-form-item>
          <el-form-item label="甲方"><el-input v-model="createForm.party_a_name" /></el-form-item>
          <el-form-item label="乙方"><el-input v-model="createForm.party_b_name" /></el-form-item>
          <el-form-item label="项目名称"><el-input v-model="createForm.project_name" /></el-form-item>
          <el-form-item label="部门"><el-input v-model="createForm.department_name" /></el-form-item>
          <el-form-item label="状态"><el-select v-model="createForm.status"><el-option label="草稿" value="draft" /><el-option label="生效中" value="active" /><el-option label="已到期" value="expired" /><el-option label="已终止" value="terminated" /></el-select></el-form-item>
          <el-form-item label="风险等级"><el-select v-model="createForm.risk_level"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /><el-option label="严重" value="critical" /></el-select></el-form-item>
        </div>
      </el-form>
      <template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveContract">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="filesVisible" :title="`${selectedContract?.name || ''} · 文件版本`" width="760px">
      <div class="file-toolbar"><span>支持 PDF、DOCX、XLSX、CSV，单文件最大 50MB</span><el-button type="primary" :icon="Upload" :loading="uploadingFile" @click="chooseFile">上传新版本</el-button><input ref="fileInput" type="file" accept=".pdf,.docx,.xlsx,.csv" hidden @change="onFileSelected" /></div>
      <el-table v-loading="filesLoading" :data="contractFiles.flatMap((item) => item.versions)">
        <el-table-column prop="original_filename" label="文件名" min-width="230" /><el-table-column prop="version_no" label="版本" width="80" />
        <el-table-column prop="size_bytes" label="大小" width="110"><template #default="{ row }">{{ formatSize(row.size_bytes) }}</template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="{ row }"><el-tag v-if="row.is_current" type="success">当前</el-tag><span v-else>历史</span></template></el-table-column>
        <el-table-column label="操作" width="180"><template #default="{ row }"><el-button text :icon="Download" @click="openVersion(row, false)">下载</el-button><el-button text @click="openVersion(row, true)">预览</el-button></template></el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="importVisible" title="导入合同" width="900px">
      <el-steps :active="importStep" finish-status="success" align-center><el-step title="选择文件" /><el-step title="预览" /><el-step title="校验" /><el-step title="确认" /></el-steps>
      <div v-if="!importPreview" class="import-empty"><p>导入不会覆盖已有合同，请先选择 XLSX 或 CSV 文件。</p><el-button type="primary" :loading="importLoading" @click="chooseImportFile">选择文件</el-button><input ref="importInput" type="file" accept=".xlsx,.csv" hidden @change="onImportSelected" /></div>
      <template v-else>
        <div class="import-meta"><span>{{ importPreview.original_filename }} · {{ importPreview.row_count }} 行</span><el-tag>{{ importPreview.status }}</el-tag></div>
        <el-table :data="importPreview.sample_rows" max-height="300"><el-table-column v-for="column in importPreview.columns" :key="column" :prop="column" :label="column" min-width="140" /></el-table>
        <el-alert v-if="importPreview.validation.errors?.length" class="import-errors" type="error" :closable="false" :title="`发现 ${importPreview.validation.errors.length} 个问题`"><div v-for="error in importPreview.validation.errors.slice(0, 20)" :key="`${error.row}-${error.field}`">第{{ error.row }}行 {{ error.field }}：{{ error.message }}</div></el-alert>
        <el-result v-if="importStep === 3" icon="success" title="导入完成" sub-title="新合同已加入台账，原有合同未被覆盖" />
      </template>
      <template #footer><el-button @click="importVisible = false">关闭</el-button><el-button v-if="importPreview && importStep === 1" type="primary" :loading="importLoading" @click="validateImport">开始校验</el-button><el-button v-if="importPreview && importStep === 2 && importPreview.validation.valid" type="primary" :loading="importLoading" @click="confirmImport">确认导入</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.contracts-view { max-width: 1400px; margin: 0 auto; }
.ledger-header, .ledger-actions, .filters, .file-toolbar, .import-meta { display: flex; align-items: center; }
.ledger-header { justify-content: space-between; gap: 24px; margin-bottom: 16px; }
.ledger-header h2 { margin: 8px 0 4px; }
.ledger-header p { margin: 0; color: #6b7280; font-size: 13px; }
.ledger-actions, .filters { gap: 10px; }
.filters { margin-bottom: 16px; flex-wrap: wrap; }
.filters .el-input { width: 280px; }
.filters .el-select { width: 150px; }
.pagination { justify-content: flex-end; margin-top: 18px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; }
.file-toolbar, .import-meta { justify-content: space-between; margin-bottom: 14px; color: #6b7280; font-size: 13px; }
.import-empty { padding: 56px 0; text-align: center; color: #6b7280; }
.import-errors { margin-top: 16px; }
@media (max-width: 760px) { .ledger-header { align-items: stretch; flex-direction: column; } .ledger-actions { flex-wrap: wrap; } .form-grid { grid-template-columns: 1fr; } .filters .el-input { width: 100%; } }
</style>
