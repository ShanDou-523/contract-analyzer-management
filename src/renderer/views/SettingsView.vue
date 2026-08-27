<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Check, CopyDocument, Delete, Plus } from '@element-plus/icons-vue'
import {
  createAnalysisTemplate,
  deleteAnalysisTemplate,
  duplicateAnalysisTemplate,
  getAnalysisTemplates,
  getSettings,
  getUsers,
  createUser,
  setDefaultAnalysisTemplate,
  updateAnalysisTemplate,
  updateSettings,
} from '../api'
import type { AnalysisField, AnalysisTemplate, AnalysisTemplateWrite, AuthUser } from '../types'

const router = useRouter()
const activeTab = ref('templates')
const savingApi = ref(false)
const loadingTemplates = ref(false)
const savingTemplate = ref(false)
const templates = ref<AnalysisTemplate[]>([])
const selectedTemplateId = ref<string | null>(null)
const users = ref<AuthUser[]>([])
const loadingUsers = ref(false)
const creatingUser = ref(false)
const userForm = reactive({ username: '', password: '', display_name: '', roles: ['viewer'] })

const currentApi = reactive({
  deepseek_api_key: '',
  baidu_ocr_api_key: '',
  baidu_ocr_secret_key: '',
})
const apiForm = reactive({
  deepseek_api_key: '',
  baidu_ocr_api_key: '',
  baidu_ocr_secret_key: '',
})
const editor = reactive<AnalysisTemplateWrite>({
  name: '',
  description: '',
  analysis_focus: '',
  fields: [],
  review_enabled: true,
  review_instructions: '',
})

function fieldId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
}

function cloneFields(fields: AnalysisField[]) {
  return fields.map((field) => ({ ...field }))
}

function selectTemplate(template: AnalysisTemplate) {
  selectedTemplateId.value = template.id
  Object.assign(editor, {
    name: template.name,
    description: template.description,
    analysis_focus: template.analysis_focus,
    fields: cloneFields(template.fields),
    review_enabled: template.review_enabled,
    review_instructions: template.review_instructions,
  })
}

async function loadTemplates(preferredId?: string) {
  loadingTemplates.value = true
  try {
    templates.value = await getAnalysisTemplates()
    const selected =
      templates.value.find((item) => item.id === preferredId) ||
      templates.value.find((item) => item.id === selectedTemplateId.value) ||
      templates.value.find((item) => item.is_default) ||
      templates.value[0]
    if (selected) selectTemplate(selected)
  } finally {
    loadingTemplates.value = false
  }
}

async function loadUsers() {
  loadingUsers.value = true
  try {
    users.value = await getUsers()
  } catch {
    users.value = []
  } finally {
    loadingUsers.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    getSettings().then((settings) => Object.assign(currentApi, settings)).catch(() => undefined),
    loadTemplates(),
    loadUsers(),
  ])
})

async function saveUser() {
  if (!userForm.username.trim() || userForm.password.length < 10 || !userForm.display_name.trim()) {
    ElMessage.warning('请填写用户名、显示名称和至少10位密码')
    return
  }
  creatingUser.value = true
  try {
    await createUser({
      username: userForm.username.trim(),
      password: userForm.password,
      display_name: userForm.display_name.trim(),
      roles: userForm.roles,
    })
    Object.assign(userForm, { username: '', password: '', display_name: '', roles: ['viewer'] })
    await loadUsers()
    ElMessage.success('用户已创建')
  } finally {
    creatingUser.value = false
  }
}

function resetApiForm() {
  apiForm.deepseek_api_key = ''
  apiForm.baidu_ocr_api_key = ''
  apiForm.baidu_ocr_secret_key = ''
}

async function saveApiSettings() {
  savingApi.value = true
  try {
    const result = await updateSettings({ ...apiForm })
    ElMessage.success(result.message)
    Object.assign(currentApi, await getSettings())
    resetApiForm()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingApi.value = false
  }
}

function newTemplate() {
  selectedTemplateId.value = null
  Object.assign(editor, {
    name: '新分析方案',
    description: '',
    analysis_focus: '',
    fields: [
      {
        id: fieldId(),
        key: 'contract_name',
        label: '合同名称',
        instruction: '提取合同标题或正式名称',
        enabled: true,
      },
    ],
    review_enabled: true,
    review_instructions: '',
  })
}

function nextFieldKey() {
  let index = editor.fields.length + 1
  let key = `custom_field_${index}`
  while (editor.fields.some((field) => field.key === key)) {
    index += 1
    key = `custom_field_${index}`
  }
  return key
}

function addField() {
  editor.fields.push({
    id: fieldId(),
    key: nextFieldKey(),
    label: '新字段',
    instruction: '',
    enabled: true,
  })
}

function removeField(index: number) {
  if (editor.fields.length <= 1) {
    ElMessage.warning('至少需要保留一个字段')
    return
  }
  editor.fields.splice(index, 1)
}

function moveField(index: number, offset: number) {
  const target = index + offset
  if (target < 0 || target >= editor.fields.length) return
  const [field] = editor.fields.splice(index, 1)
  editor.fields.splice(target, 0, field)
}

function validateTemplate() {
  if (!editor.name.trim()) return '请输入方案名称'
  if (!editor.fields.length) return '至少需要一个输出字段'
  const keys = new Set<string>()
  const labels = new Set<string>()
  for (const field of editor.fields) {
    field.key = field.key.trim()
    field.label = field.label.trim()
    field.instruction = field.instruction.trim()
    if (!/^[a-z][a-z0-9_]*$/.test(field.key)) {
      return `字段“${field.label || field.key}”的标识格式不正确`
    }
    if (!field.label) return '字段名称不能为空'
    if (keys.has(field.key)) return `字段标识“${field.key}”重复`
    if (labels.has(field.label)) return `字段名称“${field.label}”重复`
    keys.add(field.key)
    labels.add(field.label)
  }
  if (!editor.fields.some((field) => field.enabled)) return '至少需要启用一个输出字段'
  return ''
}

async function saveTemplate() {
  const error = validateTemplate()
  if (error) {
    ElMessage.warning(error)
    return
  }
  savingTemplate.value = true
  try {
    const wasUpdate = Boolean(selectedTemplateId.value)
    const payload: AnalysisTemplateWrite = {
      name: editor.name.trim(),
      description: editor.description.trim(),
      analysis_focus: editor.analysis_focus.trim(),
      fields: cloneFields(editor.fields),
      review_enabled: editor.review_enabled,
      review_instructions: editor.review_instructions.trim(),
    }
    const saved = selectedTemplateId.value
      ? await updateAnalysisTemplate(selectedTemplateId.value, payload)
      : await createAnalysisTemplate(payload)
    await loadTemplates(saved.id)
    ElMessage.success(wasUpdate ? '分析方案已保存' : '分析方案已创建')
  } finally {
    savingTemplate.value = false
  }
}

async function duplicateSelected() {
  if (!selectedTemplateId.value) return
  const copy = await duplicateAnalysisTemplate(selectedTemplateId.value)
  await loadTemplates(copy.id)
  ElMessage.success('已复制分析方案')
}

async function setSelectedDefault() {
  if (!selectedTemplateId.value) return
  await setDefaultAnalysisTemplate(selectedTemplateId.value)
  await loadTemplates(selectedTemplateId.value)
  ElMessage.success('默认分析方案已更新')
}

async function removeSelected() {
  const selected = templates.value.find((item) => item.id === selectedTemplateId.value)
  if (!selected) return
  await ElMessageBox.confirm(
    `删除方案“${selected.name}”？${selected.document_count} 份关联合同将进入“未归类”，历史分析结果仍会保留。`,
    '删除分析方案',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  )
  await deleteAnalysisTemplate(selected.id)
  selectedTemplateId.value = null
  await loadTemplates()
  ElMessage.success('分析方案已删除')
}
</script>

<template>
  <div class="settings-view">
    <div class="nav-bar">
      <el-button :icon="ArrowLeft" @click="router.back()">返回</el-button>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="分析方案" name="templates">
          <div class="template-toolbar">
            <div>
              <h2>分析方案</h2>
              <p>为不同合同类型保存独立的输出字段与审查重点。</p>
            </div>
            <el-button type="primary" :icon="Plus" @click="newTemplate">新建方案</el-button>
          </div>

          <div v-loading="loadingTemplates" class="template-layout">
            <aside class="template-list" aria-label="分析方案列表">
              <button
                v-for="template in templates"
                :key="template.id"
                type="button"
                class="template-item"
                :class="{ active: selectedTemplateId === template.id }"
                @click="selectTemplate(template)"
              >
                <span class="template-name">{{ template.name }}</span>
                <span class="template-meta">
                  <el-tag v-if="template.is_default" type="success" size="small">默认</el-tag>
                  <span>v{{ template.version }} · {{ template.fields.filter((field) => field.enabled).length }} 字段 · {{ template.document_count }} 份合同</span>
                </span>
              </button>
            </aside>

            <section class="template-editor">
              <el-empty v-if="!selectedTemplateId && !editor.fields.length" description="选择或新建一个分析方案" />
              <el-form v-else label-position="top" @submit.prevent="saveTemplate">
                <div class="editor-header">
                  <div class="editor-title">
                    <h3>{{ selectedTemplateId ? '编辑方案' : '新建方案' }}</h3>
                    <el-tag v-if="templates.find((item) => item.id === selectedTemplateId)?.is_default" type="success">默认方案</el-tag>
                  </div>
                  <div v-if="selectedTemplateId" class="editor-actions">
                    <el-button :icon="CopyDocument" @click="duplicateSelected">复制</el-button>
                    <el-button
                      v-if="!templates.find((item) => item.id === selectedTemplateId)?.is_default"
                      @click="setSelectedDefault"
                    >设为默认</el-button>
                    <el-button type="danger" plain :icon="Delete" @click="removeSelected">删除</el-button>
                  </div>
                </div>

                <div class="form-grid">
                  <el-form-item label="方案名称" required>
                    <el-input v-model="editor.name" maxlength="100" show-word-limit />
                  </el-form-item>
                  <el-form-item label="方案说明">
                    <el-input v-model="editor.description" maxlength="500" show-word-limit />
                  </el-form-item>
                </div>

                <el-form-item label="总体分析重点">
                  <el-input
                    v-model="editor.analysis_focus"
                    type="textarea"
                    :rows="3"
                    resize="vertical"
                    placeholder="说明这类合同最需要识别和判断的内容"
                  />
                </el-form-item>

                <div class="field-section-header">
                  <div>
                    <h3>输出字段</h3>
                    <p>英文标识用于稳定保存数据，中文名称用于结果页和 Excel。</p>
                  </div>
                  <el-button :icon="Plus" @click="addField">添加字段</el-button>
                </div>

                <div class="field-table-wrap">
                  <table class="field-table">
                    <thead>
                      <tr>
                        <th class="enable-column">启用</th>
                        <th>英文标识</th>
                        <th>中文名称</th>
                        <th class="instruction-column">提取说明</th>
                        <th class="order-column">顺序</th>
                        <th class="delete-column">删除</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(field, index) in editor.fields" :key="field.id">
                        <td><el-switch v-model="field.enabled" /></td>
                        <td><el-input v-model="field.key" placeholder="service_scope" /></td>
                        <td><el-input v-model="field.label" placeholder="服务范围" /></td>
                        <td><el-input v-model="field.instruction" placeholder="说明需要从合同中提取什么" /></td>
                        <td>
                          <div class="order-buttons">
                            <el-tooltip content="上移" :show-after="400">
                              <el-button text :disabled="index === 0" aria-label="上移" @click="moveField(index, -1)"><el-icon><ArrowUp /></el-icon></el-button>
                            </el-tooltip>
                            <el-tooltip content="下移" :show-after="400">
                              <el-button text :disabled="index === editor.fields.length - 1" aria-label="下移" @click="moveField(index, 1)"><el-icon><ArrowDown /></el-icon></el-button>
                            </el-tooltip>
                          </div>
                        </td>
                        <td>
                          <el-tooltip content="删除字段" :show-after="400">
                            <el-button text type="danger" aria-label="删除字段" @click="removeField(index)"><el-icon><Delete /></el-icon></el-button>
                          </el-tooltip>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <el-divider content-position="left">合理性与风险审查</el-divider>
                <el-form-item label="执行审查">
                  <el-switch v-model="editor.review_enabled" />
                </el-form-item>
                <el-form-item v-if="editor.review_enabled" label="附加审查要求">
                  <el-input
                    v-model="editor.review_instructions"
                    type="textarea"
                    :rows="4"
                    resize="vertical"
                    placeholder="填写该类合同特有的核验规则和风险判断要求"
                  />
                </el-form-item>

                <div class="save-row">
                  <el-button type="primary" :icon="Check" :loading="savingTemplate" @click="saveTemplate">保存方案</el-button>
                </div>
              </el-form>
            </section>
          </div>
        </el-tab-pane>

        <el-tab-pane label="API 设置" name="api">
          <el-form class="api-form" :model="apiForm" label-width="160px" @submit.prevent="saveApiSettings">
            <el-divider content-position="left">DeepSeek API</el-divider>
            <el-form-item label="DeepSeek API Key">
              <el-input v-model="apiForm.deepseek_api_key" type="password" show-password placeholder="sk-..." />
              <div class="form-hint">当前: {{ currentApi.deepseek_api_key || '未设置' }}</div>
            </el-form-item>
            <el-divider content-position="left">百度 OCR API</el-divider>
            <el-form-item label="API Key (Client ID)">
              <el-input v-model="apiForm.baidu_ocr_api_key" type="password" show-password placeholder="百度 OCR API Key" />
              <div class="form-hint">当前: {{ currentApi.baidu_ocr_api_key || '未设置' }}</div>
            </el-form-item>
            <el-form-item label="Secret Key">
              <el-input v-model="apiForm.baidu_ocr_secret_key" type="password" show-password placeholder="百度 OCR Secret Key" />
              <div class="form-hint">当前: {{ currentApi.baidu_ocr_secret_key || '未设置' }}</div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Check" :loading="savingApi" @click="saveApiSettings">保存 API 设置</el-button>
              <el-button @click="resetApiForm">清空输入</el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="用户管理" name="users">
          <div class="user-management">
            <div class="template-toolbar">
              <div>
                <h2>用户管理</h2>
                <p>为当前组织创建成员并分配最小必要权限。</p>
              </div>
            </div>

            <el-form class="user-form" :model="userForm" label-position="top" @submit.prevent="saveUser">
              <div class="form-grid">
                <el-form-item label="用户名" required>
                  <el-input v-model="userForm.username" autocomplete="off" placeholder="例如：zhangsan" />
                </el-form-item>
                <el-form-item label="显示名称" required>
                  <el-input v-model="userForm.display_name" placeholder="例如：张三" />
                </el-form-item>
                <el-form-item label="初始密码" required>
                  <el-input v-model="userForm.password" type="password" show-password autocomplete="new-password" placeholder="至少10位" />
                </el-form-item>
                <el-form-item label="角色" required>
                  <el-select v-model="userForm.roles" multiple collapse-tags placeholder="选择角色" style="width: 100%">
                    <el-option label="查看者" value="viewer" />
                    <el-option label="合同经理" value="contract_manager" />
                    <el-option label="审查员" value="reviewer" />
                    <el-option label="组织管理员" value="org_admin" />
                    <el-option label="系统管理员" value="system_admin" />
                  </el-select>
                </el-form-item>
              </div>
              <div class="save-row">
                <el-button type="primary" :loading="creatingUser" @click="saveUser">创建用户</el-button>
              </div>
            </el-form>

            <el-table v-loading="loadingUsers" :data="users" stripe>
              <el-table-column prop="username" label="用户名" min-width="150" />
              <el-table-column prop="display_name" label="显示名称" min-width="150" />
              <el-table-column label="角色" min-width="240">
                <template #default="{ row }">
                  <el-tag v-for="role in row.roles" :key="role" size="small" class="role-tag">{{ role }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="100" />
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.settings-view { max-width: 1200px; margin: 0 auto; }
.nav-bar { margin-bottom: 16px; }
.template-toolbar, .editor-header, .field-section-header, .editor-title, .editor-actions, .template-meta, .save-row { display: flex; align-items: center; }
.template-toolbar, .editor-header, .field-section-header { justify-content: space-between; gap: 16px; }
.template-toolbar { margin-bottom: 20px; }
.user-management { max-width: 1000px; }
.user-form { margin-bottom: 28px; }
.role-tag { margin: 2px 4px 2px 0; }
.template-toolbar h2, .template-toolbar p, .field-section-header h3, .field-section-header p { margin: 0; }
.template-toolbar h2 { font-size: 20px; }
.template-toolbar p, .field-section-header p { margin-top: 4px; color: #6b7280; font-size: 13px; }
.template-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); min-height: 620px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.template-list { padding: 8px; background: #f9fafb; border-right: 1px solid #e5e7eb; }
.template-item { display: flex; width: 100%; min-height: 64px; padding: 10px 12px; border: 0; border-radius: 6px; background: transparent; color: #374151; text-align: left; cursor: pointer; flex-direction: column; justify-content: center; gap: 7px; }
.template-item:hover { background: #f3f4f6; }
.template-item.active { background: #ecf5ff; color: #1d4ed8; }
.template-name { font-size: 14px; font-weight: 600; }
.template-meta { gap: 6px; color: #6b7280; font-size: 12px; flex-wrap: wrap; }
.template-editor { min-width: 0; padding: 24px; }
.editor-header { margin-bottom: 24px; }
.editor-title, .editor-actions { gap: 8px; }
.editor-title h3, .field-section-header h3 { margin: 0; font-size: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1.5fr; gap: 16px; }
.field-section-header { margin: 28px 0 12px; }
.field-table-wrap { overflow-x: auto; border: 1px solid #e5e7eb; border-radius: 6px; }
.field-table { width: 100%; min-width: 850px; border-collapse: collapse; table-layout: fixed; }
.field-table th { padding: 10px 8px; background: #f9fafb; color: #4b5563; font-size: 13px; font-weight: 600; text-align: left; }
.field-table td { padding: 8px; border-top: 1px solid #e5e7eb; vertical-align: middle; }
.enable-column { width: 64px; }
.instruction-column { width: 34%; }
.order-column { width: 76px; }
.delete-column { width: 56px; }
.order-buttons { display: flex; }
.order-buttons .el-button { width: 30px; margin: 0; }
.save-row { justify-content: flex-end; margin-top: 24px; }
.api-form { max-width: 720px; padding: 8px 0; }
.form-hint { color: #6b7280; font-size: 12px; margin-top: 4px; }
@media (max-width: 800px) {
  .template-layout { grid-template-columns: 1fr; }
  .template-list { display: flex; overflow-x: auto; border-right: 0; border-bottom: 1px solid #e5e7eb; }
  .template-item { min-width: 200px; }
  .template-editor { padding: 16px; }
  .form-grid { grid-template-columns: 1fr; gap: 0; }
  .editor-header, .field-section-header { align-items: flex-start; flex-direction: column; }
  .editor-actions { flex-wrap: wrap; }
}
</style>
