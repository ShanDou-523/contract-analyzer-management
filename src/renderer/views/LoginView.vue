<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const mode = ref<'login' | 'bootstrap'>('login')
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const bootstrapForm = reactive({
  organization_name: '',
  organization_code: '',
  username: '',
  password: '',
  display_name: '',
})

async function submit() {
  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.signIn(form.username, form.password)
    } else {
      await auth.bootstrap(bootstrapForm)
    }
    await router.replace('/')
  } catch {
    ElMessage.error(mode.value === 'login' ? '用户名或密码错误' : '初始化失败，请检查输入')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h1>合同分析系统</h1>
      <el-tabs v-model="mode" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form @submit.prevent="submit">
            <el-form-item label="用户名"><el-input v-model="form.username" autocomplete="username" /></el-form-item>
            <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" /></el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" class="login-submit">登录</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="首次初始化" name="bootstrap">
          <el-alert title="仅在系统尚未创建用户时可用" type="info" :closable="false" />
          <el-form @submit.prevent="submit">
            <el-form-item label="组织名称"><el-input v-model="bootstrapForm.organization_name" /></el-form-item>
            <el-form-item label="组织编码"><el-input v-model="bootstrapForm.organization_code" /></el-form-item>
            <el-form-item label="管理员用户名"><el-input v-model="bootstrapForm.username" autocomplete="username" /></el-form-item>
            <el-form-item label="显示名称"><el-input v-model="bootstrapForm.display_name" /></el-form-item>
            <el-form-item label="管理员密码"><el-input v-model="bootstrapForm.password" type="password" show-password autocomplete="new-password" /></el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" class="login-submit">创建管理员</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped>
.login-page { min-height: 70vh; display: grid; place-items: center; }
.login-card { width: min(440px, 100%); }
.login-card h1 { margin: 0 0 20px; text-align: center; }
.login-submit { width: 100%; }
</style>
