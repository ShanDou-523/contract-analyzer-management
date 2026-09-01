<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { Delete, Search } from '@element-plus/icons-vue'
import { assignDocumentTemplate, createBatchImport, getAnalysisTemplates, getBatchImport, listBatchImports, retryBatchItem, retryFailedBatchItems, runAnalysis, runOcr } from '../api'
import { useDocumentsStore } from '../stores/documents'
import type { AnalysisTemplate, BatchImport, DocumentListItem } from '../types'

const router = useRouter()
const store = useDocumentsStore()
const fileInputRef = ref<HTMLInputElement | null>(null)
const batchFileInputRef = ref<HTMLInputElement | null>(null)
const isDragover = ref(false)
const templates = ref<AnalysisTemplate[]>([])
const templatesLoading = ref(false)
const selectedTemplateId = ref('')
const batchFiles = ref<File[]>([])
const batchImport = ref<BatchImport | null>(null)
const batchLoading = ref(false)
let batchTimer: ReturnType<typeof setInterval> | null = null
let batchPollInFlight = false
const assignmentDraft = ref<Record<string, string>>({})
const initializing = ref(true)
const searchKeyword = ref('')
const activeSearchKeyword = ref('')

const ALL_TEMPLATES = 'all'
const UNASSIGNED = 'unassigned'

const documents = computed(() => store.documents)
const documentTotal = computed(() => store.total)
const loading = computed(() => store.loading)
const processingStep = computed(() => store.processingStep)
const progressPercent = computed(() => store.progressPercent)
const activeStep = computed(
  () => ({ idle: 0, uploading: 0, ocr: 1, analyzing: 2, done: 3 })[processingStep.value] ?? 0,
)

const selectedTemplate = computed(() =>
  templates.value.find((template) => template.id === selectedTemplateId.value),
)
const filterLabel = computed(() => {
  if (activeSearchKeyword.value) return `全局搜索“${activeSearchKeyword.value}”`
  if (selectedTemplateId.value === ALL_TEMPLATES) return '全部方案'
  if (selectedTemplateId.value === UNASSIGNED) return '未归类'
  return selectedTemplate.value?.name || '未选择方案'
})
const canProcess = computed(() => Boolean(selectedTemplate.value))
const isProcessing = computed(() =>
  ['uploading', 'ocr', 'analyzing'].includes(processingStep.value),
)
function batchStatusLabel(status: string) { return ({ queued: '排队中', running: '处理中', completed: '已完成', partial: '部分失败', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] || status }
function batchItemStatusLabel(status: string) { return ({ queued: '排队中', ocr_processing: 'OCR中', ocr_done: '待分析', analyzing: '分析中', done: '已完成', error: '失败' } as Record<string, string>)[status] || status }
function selectBatchFiles() { batchFileInputRef.value?.click() }
const emptyText = computed(() => {
  if (activeSearchKeyword.value) return `没有找到包含“${activeSearchKeyword.value}”的合同`
  if (selectedTemplateId.value === UNASSIGNED) return '暂无未归类合同'
  if (selectedTemplateId.value === ALL_TEMPLATES) return '暂无合同，请上传PDF合同'
  return `暂无${filterLabel.value}合同，请上传PDF合同`
})

async function refreshDocuments() {
  await store.fetchDocuments(
    selectedTemplateId.value || undefined,
    activeSearchKeyword.value || undefined,
  )
}

async function executeGlobalSearch() {
  activeSearchKeyword.value = searchKeyword.value.trim()
  await refreshDocuments()
}

async function clearGlobalSearch() {
  searchKeyword.value = ''
  activeSearchKeyword.value = ''
  await refreshDocuments()
}

onMounted(async () => {
  // A completed upload should not lock the home page after returning from results.
  if (store.processingStep === 'done') {
    store.processingStep = 'idle'
    store.progressPercent = 0
  }
  templatesLoading.value = true
  initializing.value = true
  try {
    const loadedTemplates = await getAnalysisTemplates()
    templates.value = loadedTemplates
    const remembered = localStorage.getItem('contract-analyzer-template-id')
    selectedTemplateId.value =
      templates.value.find((item) => item.id === remembered)?.id ||
      (remembered === ALL_TEMPLATES || remembered === UNASSIGNED ? remembered : '') ||
      templates.value.find((item) => item.is_default)?.id ||
      templates.value[0]?.id ||
      ALL_TEMPLATES
    const recentBatches = await listBatchImports({ page: 1, page_size: 1 })
    if (recentBatches.items[0]) {
      batchImport.value = recentBatches.items[0]
      if (['queued', 'running'].includes(batchImport.value.status)) startBatchPolling()
    }
    await refreshDocuments()
  } finally {
    initializing.value = false
    templatesLoading.value = false
  }
})

onBeforeUnmount(() => { if (batchTimer) clearInterval(batchTimer) })

watch(selectedTemplateId, async (value, previous) => {
  if (!value || value === previous) return
  localStorage.setItem('contract-analyzer-template-id', value)
  if (!initializing.value && !isProcessing.value) await refreshDocuments()
})

function selectFile() {
  if (!canProcess.value) {
    ElMessage.warning('请先选择一个具体分析方案后再上传合同')
    return
  }
  fileInputRef.value?.click()
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) processFile(input.files[0])
}

function onBatchFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  batchFiles.value = Array.from(input.files || [])
  input.value = ''
}

async function submitBatchImport() {
  if (!canProcess.value) {
    ElMessage.warning('请先选择一个具体分析方案')
    return
  }
  if (!batchFiles.value.length) {
    ElMessage.warning('请先选择要导入的PDF文件')
    return
  }
  const invalid = batchFiles.value.find((file) => !file.name.toLowerCase().endsWith('.pdf') || file.size > 50 * 1024 * 1024)
  if (invalid) {
    ElMessage.error(`文件 ${invalid.name} 不是PDF或超过50MB限制`)
    return
  }
  batchLoading.value = true
  try {
    batchImport.value = await createBatchImport(batchFiles.value, selectedTemplateId.value)
    batchFiles.value = []
    startBatchPolling()
    ElMessage.success('批量导入已排队，后台将依次完成OCR和AI分析')
  } finally {
    batchLoading.value = false
  }
}

function startBatchPolling() {
  if (batchTimer) clearInterval(batchTimer)
  const poll = async () => {
    if (!batchImport.value || batchPollInFlight) return
    batchPollInFlight = true
    const batchId = batchImport.value.id
    try {
      const current = await getBatchImport(batchId, { suppressNetworkErrorToast: true })
      // Ignore a late response if the user has already started another batch.
      if (!batchImport.value || batchImport.value.id !== batchId) return
      batchImport.value = current
      if (['completed', 'partial', 'failed', 'cancelled'].includes(current.status)) {
        if (batchTimer) clearInterval(batchTimer)
        batchTimer = null
        await refreshDocuments()
      }
    } catch {
      // Polling is best-effort; the next tick retries without interrupting the batch.
    } finally {
      batchPollInFlight = false
    }
  }
  void poll()
  batchTimer = setInterval(() => { void poll() }, 3000)
}

async function retryBatchItemAction(itemId: string) {
  if (!batchImport.value) return
  batchImport.value = await retryBatchItem(batchImport.value.id, itemId)
  startBatchPolling()
}

async function retryBatchFailed() {
  if (!batchImport.value) return
  batchImport.value = await retryFailedBatchItems(batchImport.value.id)
  startBatchPolling()
}

function onDrop(event: DragEvent) {
  isDragover.value = false
  if (event.dataTransfer?.files.length) processFile(event.dataTransfer.files[0])
}

async function processFile(file: File) {
  if (!canProcess.value) {
    ElMessage.warning('请先选择一个具体分析方案，不能使用“全部方案”或“未归类”上传')
    return
  }
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('仅支持PDF文件格式')
    return
  }
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小超过50MB限制')
    return
  }

  store.processingStep = 'uploading'
  store.progressPercent = 10
  try {
    const document = await store.uploadDocument(file, selectedTemplateId.value)
    if (!document) return

    store.processingStep = 'ocr'
    await runOcr(document.id)
    store.updateDocumentStatus(document.id, 'ocr_done')
    store.progressPercent = 70
    store.processingStep = 'analyzing'
    await runAnalysis(document.id, selectedTemplateId.value)
    store.updateDocumentStatus(document.id, 'done')
    store.progressPercent = 100
    store.processingStep = 'done'

    ElNotification({
      title: '处理完成',
      message: `合同 "${document.original_filename}" 分析完成`,
      type: 'success',
    })
    router.push(`/documents/${document.id}`)
  } catch {
    store.processingStep = 'idle'
    store.progressPercent = 0
  } finally {
    // Keep the result state in the document, not in the home-page workflow state.
    store.processingStep = 'idle'
    store.progressPercent = 0
  }
}

async function startOcr(document: DocumentListItem) {
  try {
    store.updateDocumentStatus(document.id, 'ocr_processing')
    const result = await runOcr(document.id)
    store.updateDocumentStatus(document.id, 'ocr_done')
    ElMessage.success(`OCR完成，识别了${result.page_count}页，共${result.text_length}字符`)
    await refreshDocuments()
  } catch {
    store.updateDocumentStatus(document.id, 'error')
  }
}

async function startAnalysis(document: DocumentListItem) {
  const analysisTemplateId = selectedTemplate.value?.id || document.analysis_template_id
  if (!analysisTemplateId) {
    ElMessage.warning('请先将合同归类到一个分析方案')
    return
  }
  try {
    store.updateDocumentStatus(document.id, 'analyzing')
    await runAnalysis(document.id, analysisTemplateId)
    store.updateDocumentStatus(document.id, 'done')
    ElMessage.success('AI分析完成')
    await refreshDocuments()
    router.push(`/documents/${document.id}`)
  } catch {
    store.updateDocumentStatus(document.id, 'error')
  }
}

async function assignDocument(id: string) {
  const templateId = assignmentDraft.value[id]
  if (!templateId) return
  try {
    await assignDocumentTemplate(id, templateId)
    delete assignmentDraft.value[id]
    ElMessage.success('合同已归类')
    await refreshDocuments()
  } catch {
    ElMessage.error('归类失败')
  }
}

async function removeDocument(id: string) {
  await store.removeDocument(id)
  ElMessage.success('文档已删除')
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value: string | null) {
  return value
    ? new Date(value).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '-'
}
</script>

<template>
  <div class="home-view">
    <el-card class="upload-card" shadow="hover">
      <div class="template-picker">
        <div class="template-picker-copy">
          <span class="template-picker-label">当前分析方案 / 列表筛选</span>
          <span class="template-picker-description">
            {{ selectedTemplate?.description || '查看全部方案或整理未归类合同' }}
          </span>
        </div>
        <el-select
          v-model="selectedTemplateId"
          :loading="templatesLoading"
          placeholder="选择分析方案"
          class="template-select"
          :disabled="isProcessing"
        >
          <el-option label="全部方案" :value="ALL_TEMPLATES" />
          <el-option label="未归类" :value="UNASSIGNED" />
          <el-option v-for="template in templates" :key="template.id" :label="template.name" :value="template.id">
            <span>{{ template.name }}</span>
            <el-tag v-if="template.is_default" type="success" size="small" style="margin-left: 8px">默认</el-tag>
          </el-option>
        </el-select>
      </div>
      <div
        class="upload-area"
        :class="{ 'is-dragover': isDragover, 'is-disabled': !canProcess }"
        @dragover.prevent="isDragover = true"
        @dragleave.prevent="isDragover = false"
        @drop.prevent="onDrop"
        @click="selectFile"
      >
        <input ref="fileInputRef" type="file" accept=".pdf" hidden @change="onFileChange" />
        <el-icon class="upload-icon" :size="48" color="#409EFF"><UploadFilled /></el-icon>
        <p class="upload-text">{{ canProcess ? '点击或拖拽 PDF 合同文件到此处' : '选择一个具体分析方案后可上传合同' }}</p>
        <p class="upload-hint">支持 PDF 格式，最大 50MB</p>
      </div>

      <div class="batch-toolbar">
        <input ref="batchFileInputRef" type="file" accept=".pdf" multiple hidden @change="onBatchFileChange" />
        <el-button :disabled="!canProcess" @click="selectBatchFiles">选择多个PDF</el-button>
        <span class="batch-selection">{{ batchFiles.length ? `已选择 ${batchFiles.length} 个文件` : '可一次选择多个PDF，后台逐个OCR并分析' }}</span>
        <el-button v-if="batchFiles.length" type="primary" :loading="batchLoading" @click="submitBatchImport">开始批量处理</el-button>
      </div>

      <div v-if="processingStep !== 'idle'" class="progress-section">
        <el-steps :active="activeStep" finish-status="success" align-center>
          <el-step title="上传" description="文件上传" />
          <el-step title="OCR识别" description="文字识别" />
          <el-step title="AI分析" description="DeepSeek分析" />
          <el-step title="完成" description="查看结果" />
        </el-steps>
        <el-progress
          :percentage="progressPercent"
          :status="progressPercent === 100 ? 'success' : ''"
          :stroke-width="8"
          style="margin-top: 16px"
        />
      </div>

      <div v-if="batchImport" class="batch-progress-section">
        <div class="batch-heading">
          <div><strong>批次进度</strong><span class="muted">{{ batchImport.completed_count }}/{{ batchImport.total_count }} 已完成<span v-if="batchImport.failed_count">，{{ batchImport.failed_count }} 个失败</span></span></div>
          <div class="batch-actions"><el-tag :type="batchImport.status === 'completed' ? 'success' : batchImport.status === 'failed' || batchImport.status === 'partial' ? 'danger' : 'warning'">{{ batchStatusLabel(batchImport.status) }}</el-tag><el-button v-if="batchImport.failed_count" text type="primary" @click="retryBatchFailed">重试失败项</el-button></div>
        </div>
        <el-progress :percentage="batchImport.progress" :status="batchImport.status === 'completed' ? 'success' : batchImport.status === 'failed' ? 'exception' : undefined" />
        <el-table :data="batchImport.items" size="small" class="batch-table">
          <el-table-column prop="original_filename" label="文件名" min-width="220" />
          <el-table-column label="阶段" width="110"><template #default="{ row }">{{ row.stage === 'ocr' ? 'OCR识别' : 'AI分析' }}</template></el-table-column>
          <el-table-column label="进度" width="150"><template #default="{ row }"><el-progress :percentage="row.progress" :status="row.status === 'error' ? 'exception' : row.status === 'done' ? 'success' : undefined" /></template></el-table-column>
          <el-table-column label="状态" width="120"><template #default="{ row }">{{ batchItemStatusLabel(row.status) }}</template></el-table-column>
          <el-table-column label="错误/操作" min-width="220"><template #default="{ row }"><span v-if="row.error_message" class="danger">{{ row.error_message }}</span><el-button v-if="row.status === 'error' && row.document_id" text type="primary" @click="retryBatchItemAction(row.id)">重试</el-button><span v-if="!row.error_message && row.status !== 'error'" class="muted">-</span></template></el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card class="list-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="card-title">
            <el-icon><List /></el-icon> {{ filterLabel }} · 文档
            <el-tag type="info" size="small">{{ documentTotal }} 份</el-tag>
          </span>
          <div class="list-tools">
            <el-input
              v-model="searchKeyword"
              clearable
              class="global-search"
              placeholder="全局搜索合同名"
              @clear="clearGlobalSearch"
              @keyup.enter="executeGlobalSearch"
            >
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-button type="primary" :loading="loading" :icon="Search" @click="executeGlobalSearch">搜索</el-button>
            <el-button text type="primary" :loading="loading" @click="refreshDocuments">
              <el-icon><Refresh /></el-icon> 刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="documents" style="width: 100%" :empty-text="emptyText">
        <el-table-column prop="original_filename" label="文件名" min-width="200">
          <template #default="{ row }">
            <el-icon color="#E6A23C"><Document /></el-icon>
            <span style="margin-left: 8px">{{ row.original_filename }}</span>
          </template>
        </el-table-column>
        <el-table-column label="方案" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.analysis_template_id" size="small" type="success">
              {{ row.analysis_template_name }}<span v-if="row.analysis_template_version"> v{{ row.analysis_template_version }}</span>
            </el-tag>
            <el-tag v-else size="small" type="warning">
              未归类<span v-if="row.analysis_template_name"> · {{ row.analysis_template_name }}</span>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'uploaded'" type="info">已上传</el-tag>
            <el-tag v-else-if="row.status === 'ocr_processing'" type="warning"><el-icon class="is-loading"><Loading /></el-icon> OCR识别中</el-tag>
            <el-tag v-else-if="row.status === 'ocr_done'" type="primary">已识别</el-tag>
            <el-tag v-else-if="row.status === 'analyzing'" type="warning"><el-icon class="is-loading"><Loading /></el-icon> AI分析中</el-tag>
            <el-tag v-else-if="row.status === 'done'" type="success">已完成</el-tag>
            <el-tag v-else-if="row.status === 'error'" type="danger">出错</el-tag>
            <el-tag v-else type="info">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="page_count" label="页数" width="80">
          <template #default="{ row }">{{ row.page_count ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="file_size" label="文件大小" width="110">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-select
              v-if="!row.analysis_template_id"
              v-model="assignmentDraft[row.id]"
              size="small"
              placeholder="归类到方案"
              style="width: 130px; margin-right: 6px"
              @change="assignDocument(row.id)"
            >
              <el-option v-for="template in templates" :key="template.id" :label="template.name" :value="template.id" />
            </el-select>
            <el-button v-if="row.status === 'uploaded'" type="primary" size="small" @click="startOcr(row)">开始OCR</el-button>
            <el-button v-if="row.status === 'ocr_done'" type="success" size="small" @click="startAnalysis(row)">开始分析</el-button>
            <el-button v-if="row.status === 'done'" type="primary" size="small" @click="router.push(`/documents/${row.id}`)">查看结果</el-button>
            <el-popconfirm title="确认删除此文档？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeDocument(row.id)">
              <template #reference><el-button type="danger" size="small" :icon="Delete">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.home-view { max-width: 1200px; margin: 0 auto; }
.upload-card { margin-bottom: 24px; }
.template-picker { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding-bottom: 20px; margin-bottom: 20px; border-bottom: 1px solid #ebeef5; }
.template-picker-copy { display: flex; min-width: 0; flex-direction: column; gap: 4px; }
.template-picker-label { color: #303133; font-size: 15px; font-weight: 600; }
.template-picker-description { max-width: 620px; overflow: hidden; color: #6b7280; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.template-select { width: 260px; flex: 0 0 260px; }
.upload-area { border: 2px dashed #d9d9d9; border-radius: 8px; padding: 48px 24px; text-align: center; cursor: pointer; transition: all 0.3s; background: #fafafa; }
.upload-area:hover, .upload-area.is-dragover { border-color: #409eff; background: #ecf5ff; }
.upload-area.is-disabled { border-color: #e5e7eb; background: #f9fafb; cursor: not-allowed; }
.upload-area.is-disabled:hover { border-color: #e5e7eb; background: #f9fafb; }
.upload-area.is-disabled .upload-icon { opacity: 0.45; }
.upload-icon { margin-bottom: 16px; }
.upload-text { font-size: 16px; color: #606266; margin-bottom: 8px; }
.upload-hint { font-size: 13px; color: #999; }
.batch-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
.batch-selection { color: #6b7280; font-size: 13px; }
.batch-progress-section { margin-top: 20px; padding-top: 18px; border-top: 1px solid #ebeef5; }
.batch-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 12px; }
.batch-heading > div:first-child { display: flex; align-items: center; gap: 12px; }
.batch-actions { display: flex; align-items: center; gap: 10px; }
.batch-table { margin-top: 14px; }
.muted { color: #909399; font-size: 12px; }
.danger { color: #f56c6c; }
.progress-section { margin-top: 24px; padding-top: 24px; border-top: 1px solid #ebeef5; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.list-tools { display: flex; align-items: center; gap: 8px; }
.global-search { width: 240px; }
@media (max-width: 640px) {
  .template-picker { align-items: stretch; flex-direction: column; gap: 12px; }
  .template-select { width: 100%; flex-basis: auto; }
  .card-header { align-items: stretch; flex-direction: column; gap: 12px; }
  .list-tools { width: 100%; flex-wrap: wrap; }
  .global-search { min-width: 0; width: auto; flex: 1 1 180px; }
  .batch-heading { align-items: flex-start; flex-direction: column; }
  .batch-heading > div:first-child { align-items: flex-start; flex-direction: column; gap: 4px; }
}
</style>
