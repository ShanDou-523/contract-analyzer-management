<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div id="app-container">
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
          <el-button text @click="router.push('/settings')">
            <el-icon><Setting /></el-icon>
            设置
          </el-button>
        </div>
      </el-header>
      <el-main class="app-main"><router-view /></el-main>
      <el-footer class="app-footer">合同分析系统 v1.0 — 基于 DeepSeek AI</el-footer>
    </el-container>
  </div>
</template>
