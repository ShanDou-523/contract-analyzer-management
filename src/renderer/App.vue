<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const isLogin = computed(() => route.name === 'login')

async function signOut() {
  await auth.signOut()
  await router.replace('/login')
}
</script>

<template>
  <div id="app-container">
    <router-view v-if="isLogin" />
    <template v-else>
    <el-container class="app-layout">
      <el-header class="app-header">
        <div class="header-left">
          <el-icon :size="28" color="#409EFF"><Document /></el-icon>
          <h1 class="app-title">合同分析系统</h1>
        </div>
        <div class="header-right">
          <el-button text @click="router.push('/')">
            <el-icon><HomeFilled /></el-icon>
            首页
          </el-button>
          <el-button text @click="router.push('/contracts')">
            <el-icon><Tickets /></el-icon>
            合同台账
          </el-button>
          <el-button text @click="router.push('/fulfillment')">
            <el-icon><DataLine /></el-icon>
            履约看板
          </el-button>
          <el-button text @click="router.push('/settings')">
            <el-icon><Setting /></el-icon>
            设置
          </el-button>
          <el-button text @click="signOut">退出</el-button>
        </div>
      </el-header>
      <el-main class="app-main"><router-view /></el-main>
      <el-footer class="app-footer">合同分析系统 v1.0 — 基于 DeepSeek AI</el-footer>
    </el-container>
    </template>
  </div>
</template>
