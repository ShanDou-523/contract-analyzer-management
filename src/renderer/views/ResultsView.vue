<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import { getAnalysisTemplates, initApi, runAnalysis } from '../api'
import { useDocumentsStore } from '../stores/documents'
import type { AnalysisTemplate } from '../types'

const route = useRoute()
const router = useRouter()
const store = useDocumentsStore()
const documentId = computed(() => route.params.id as string)
const document = computed(() => store.currentDocument)
const loading = computed(() => store.loading)
const analyzing = ref(false)
const exporting = ref(false)
const showOcr = ref(false)
const templates = ref<AnalysisTemplate[]>([])
const selectedTemplateId = ref('')

const attributeRecord = computed(() =>
  document.value?.analysis_results?.find((item) => item.prompt_type === 'attribute_extraction'),
)

function parseResult(promptType: string): any | null {
  const result = document.value?.analysis_results?.find((item) => item.prompt_type === promptType)
  if (!result?.response_text) return null
  try {
    let text = result.response_text
    const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/)
    if (fenced) text = fenced[1]
    return JSON.parse(text.trim())
  } catch {
    return null
  }
}

const attributeResult = computed(() => parseResult('attribute_extraction'))
const reviewResult = computed(() => parseResult('reasonability_check'))
const sortedIssues = computed(() => {
  const issues = reviewResult.value?.数据问题 || []
  const order: Record<string, number> = { 严重: 0, 警告: 1, 注意: 2, 否: 99 }
  return [...issues].sort((a, b) => (order[a.严重程度] ?? 99) - (order[b.严重程度] ?? 99))
})
const severityCounts = computed(() => {
  const counts: Record<string, number> = { 严重: 0, 警告: 0, 注意: 0 }
  for (const issue of sortedIssues.value) {
    if (issue.是否有问题 === '是') {
      const severity = issue.严重程度 || '警告'
      counts[severity] = (counts[severity] || 0) + 1
    }
  }
  return counts
})
const attributeRows = computed(() => {
  if (!attributeResult.value) return []
  const fields = attributeRecord.value?.fields_snapshot
  if (fields?.length) {
    return fields.map((field) => ({
      key: field.key,
      label: field.label,
      value: formatAttributeValue(attributeResult.value[field.key]),
    }))
  }
  return Object.entries(attributeResult.value).map(([key, value]) => ({
    key,
    label: key,
    value: formatAttributeValue(value),
  }))
})

const analysisTemplateLabel = computed(() => {
  if (document.value?.analysis_template_name) {
    return `${document.value.analysis_template_name}${document.value.analysis_template_version ? ` v${document.value.analysis_template_version}` : ''}`
  }
  return '未归类'
})
const resultTemplateLabel = computed(() => {
  const record = attributeRecord.value
  return record?.template_name
    ? `${record.template_name}${record.template_version ? ` v${record.template_version}` : ''}`
    : '旧版结果'
})

function formatAttributeValue(value: unknown) {
  if (value === undefined || value === null || value === '') return '未提及'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

function rowClassName({ row }: any) {
  if (row.是否有问题 !== '是') return ''
  if (row.严重程度 === '严重') return 'row-severe'
  if (row.严重程度 === '警告') return 'row-warning'
  return 'row-notice'
}

function severityTag(severity: string) {
  return severity === '严重' ? 'danger' : severity === '警告' ? 'warning' : 'info'
}

function severityClass(severity: string) {
  return severity === '严重' ? 'text-red bold' : severity === '警告' ? 'text-orange' : ''
}

async function fetchDocument() {
  await store.fetchDocument(documentId.value)
}

async function initialize() {
  const [, loadedTemplates] = await Promise.all([fetchDocument(), getAnalysisTemplates()])
  templates.value = loadedTemplates
  const previousTemplateId = attributeRecord.value?.template_id
  selectedTemplateId.value =
    templates.value.find((item) => item.id === previousTemplateId)?.id ||
    templates.value.find((item) => item.is_default)?.id ||
    templates.value[0]?.id ||
    ''
}

onMounted(initialize)
watch(documentId, initialize)

async function analyze() {
  if (!selectedTemplateId.value) {
    ElMessage.warning('请先选择分析方案')
    return
  }
  analyzing.value = true
  try {
    await runAnalysis(documentId.value, selectedTemplateId.value)
    store.updateDocumentStatus(documentId.value, 'done')
    ElMessage.success('AI分析完成')
    await fetchDocument()
  } catch {
    ElMessage.error('分析失败')
  } finally {
    analyzing.value = false
  }
}

async function exportExcel() {
  exporting.value = true
  try {
    const filename = `${(document.value?.original_filename || '合同').replace(/\.pdf$/i, '')}_分析结果.xlsx`
    if (window.electronAPI?.saveExcelFile) {
      const result = await window.electronAPI.saveExcelFile(documentId.value, filename)
      if (result.canceled) return
      result.success
        ? ElMessage.success(`已导出到: ${result.path}`)
        : ElMessage.error(`导出失败: ${result.error || '未知错误'}`)
    } else {
      const response = await (await initApi()).get(`/api/export/${documentId.value}`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([response.data]))
      const anchor = window.document.createElement('a')
      anchor.href = url
      anchor.download = filename
      anchor.click()
      URL.revokeObjectURL(url)
      ElMessage.success('Excel 导出成功')
    }
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
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
  <div class="results-view">
    <div class="nav-bar"><el-button :icon="ArrowLeft" @click="router.push('/')">返回列表</el-button></div>

    <el-card v-loading="loading" class="info-card" shadow="hover">
      <template #header><span class="card-title"><el-icon><Document /></el-icon> {{ document?.original_filename }}</span></template>
      <el-descriptions v-if="document" :column="4" border size="small">
        <el-descriptions-item label="状态">
          <el-tag v-if="document.status === 'done'" type="success">已完成</el-tag>
          <el-tag v-else-if="document.status === 'analyzing'" type="warning">分析中</el-tag>
          <el-tag v-else type="info">{{ document.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="页数">{{ document.page_count ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="大小">{{ formatSize(document.file_size) }}</el-descriptions-item>
        <el-descriptions-item label="上传时间">{{ formatDate(document.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="当前归属方案">{{ analysisTemplateLabel }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="attributeResult" class="result-card" shadow="hover">
      <template #header>
        <span class="card-title">合同属性提取 <el-tag type="info" size="small">{{ resultTemplateLabel }}</el-tag></span>
      </template>
      <el-table :data="attributeRows" border stripe style="width: 100%">
        <el-table-column prop="label" label="属性" width="140" />
        <el-table-column prop="value" label="内容" />
      </el-table>
    </el-card>

    <el-card v-if="reviewResult?.数据问题?.length" class="result-card" shadow="hover">
      <template #header>
        <span class="card-title">
          <el-icon color="#E6A23C"><WarningFilled /></el-icon> 数据问题审查
          <el-tag v-if="severityCounts.严重 > 0" type="danger" size="small" style="margin-left: 8px">严重 {{ severityCounts.严重 }}</el-tag>
          <el-tag v-if="severityCounts.警告 > 0" type="warning" size="small" style="margin-left: 4px">警告 {{ severityCounts.警告 }}</el-tag>
        </span>
      </template>
      <el-table :data="sortedIssues" border stripe style="width: 100%" :row-class-name="rowClassName">
        <el-table-column prop="项目" label="项目" width="100" />
        <el-table-column prop="合同标注" label="合同标注" width="130">
          <template #default="{ row }"><span :class="{ 'text-red': row.严重程度 === '严重' && row.是否有问题 === '是' }">{{ row.合同标注 }}</span></template>
        </el-table-column>
        <el-table-column label="验算公式" width="200">
          <template #default="{ row }"><span v-if="row.验算公式 || row['描述/公式']" class="formula-text">{{ row.验算公式 || row['描述/公式'] }}</span><span v-else style="color: #999">—</span></template>
        </el-table-column>
        <el-table-column label="验算结果" width="120">
          <template #default="{ row }"><span v-if="row.验算结果 || row.计算结果" :class="{ 'text-red bold': row.严重程度 === '严重' && row.是否有问题 === '是' }">{{ row.验算结果 || row.计算结果 }}</span><span v-else style="color: #999">—</span></template>
        </el-table-column>
        <el-table-column label="审查说明" min-width="200">
          <template #default="{ row }">
            <div v-if="row.是否有问题 === '是'">
              <el-tag :type="severityTag(row.严重程度)" size="small" effect="dark">{{ row.严重程度 || '警告' }}</el-tag>
              <span :class="severityClass(row.严重程度)" style="margin-left: 6px">{{ row.说明 }}</span>
            </div>
            <span v-else style="color: #67C23A"><el-icon><SuccessFilled /></el-icon> {{ row.说明 || '正常' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="sortedIssues.filter((item) => item.是否有问题 === '是').length === 0" class="all-ok">
        <el-icon color="#67C23A"><SuccessFilled /></el-icon> 各项数据暂未发现明显问题
      </div>
    </el-card>

    <el-card v-if="reviewResult?.内容合理性?.length" class="result-card" shadow="hover">
      <template #header><span class="card-title">内容合理性审查</span></template>
      <div v-for="(item, index) in reviewResult.内容合理性" :key="index" class="review-item">
        <h4>{{ item.方面 }}</h4>
        <p><strong>评价：</strong>{{ item.评价 }}</p>
        <p v-if="item.建议"><strong>建议：</strong>{{ item.建议 }}</p>
      </div>
      <div v-if="reviewResult?.总结" class="review-summary"><el-alert :title="reviewResult.总结" type="warning" :closable="false" show-icon /></div>
    </el-card>

    <el-card v-if="document?.ocr_text" class="ocr-card" shadow="hover">
      <template #header><div class="card-header-row"><span class="card-title">OCR 原始文本</span><el-button text type="primary" @click="showOcr = !showOcr">{{ showOcr ? '收起' : '展开' }}</el-button></div></template>
      <div v-show="showOcr" class="ocr-text"><pre>{{ document?.ocr_text }}</pre></div>
    </el-card>

    <el-card v-if="!loading && !attributeResult && !reviewResult && document" shadow="hover">
      <el-empty v-if="document.status === 'ocr_done'" description="OCR已完成，点击下方按钮开始AI分析"><el-button type="primary" :loading="analyzing" @click="analyze">开始AI分析</el-button></el-empty>
      <el-empty v-else description="文档尚未完成OCR，无法查看结果" />
    </el-card>

    <div v-if="document" class="actions-bar">
      <div v-if="document.status === 'done' || document.status === 'ocr_done'" class="reanalyze-template">
        <span>分析方案</span>
        <el-select v-model="selectedTemplateId" placeholder="选择分析方案" style="width: 240px">
          <el-option v-for="template in templates" :key="template.id" :label="template.name" :value="template.id">
            <span>{{ template.name }}</span>
            <el-tag v-if="template.is_default" type="success" size="small" style="margin-left: 8px">默认</el-tag>
          </el-option>
        </el-select>
      </div>
      <el-button v-if="document.status === 'done' || document.status === 'ocr_done'" type="primary" :loading="analyzing" @click="analyze">{{ document.status === 'done' ? '重新分析' : '开始AI分析' }}</el-button>
      <el-button v-if="document.status === 'done'" type="success" :loading="exporting" @click="exportExcel"><el-icon><Download /></el-icon> 导出 Excel</el-button>
    </div>
  </div>
</template>

<style scoped>
.results-view { max-width: 1000px; margin: 0 auto; }
.nav-bar, .info-card, .result-card { margin-bottom: 16px; }
.card-title { font-size: 16px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.ocr-card { margin-bottom: 16px; }
.ocr-text { max-height: 400px; overflow-y: auto; background: #f5f7fa; border-radius: 4px; padding: 16px; }
.ocr-text pre { white-space: pre-wrap; font-size: 13px; line-height: 1.8; color: #606266; }
.review-item { padding: 12px 0; border-bottom: 1px solid #ebeef5; }
.review-item:last-child { border-bottom: none; }
.review-item h4 { margin: 0 0 8px; color: #303133; font-size: 15px; }
.review-item p { margin: 4px 0; color: #606266; line-height: 1.7; }
.review-summary { margin-top: 16px; }
.all-ok { padding: 24px; text-align: center; color: #67c23a; font-size: 15px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.actions-bar { display: flex; align-items: center; justify-content: center; gap: 12px; padding: 16px 0; flex-wrap: wrap; }
.reanalyze-template { display: flex; align-items: center; gap: 8px; color: #606266; font-size: 14px; }
:deep(.row-severe) { background: #fef0f0 !important; }
:deep(.row-severe:hover > td) { background: #fde2e2 !important; }
:deep(.row-warning) { background: #fdf6ec !important; }
:deep(.row-warning:hover > td) { background: #faecd8 !important; }
:deep(.row-notice) { background: #f4f4f5 !important; }
.text-red { color: #f56c6c; }
.text-orange { color: #e6a23c; }
.bold { font-weight: 700; }
.formula-text { color: #606266; font-family: Consolas, 'Courier New', monospace; font-size: 13px; }
@media (max-width: 640px) {
  .reanalyze-template { width: 100%; align-items: stretch; flex-direction: column; }
  .reanalyze-template :deep(.el-select) { width: 100% !important; }
}
</style>
