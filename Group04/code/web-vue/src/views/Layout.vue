<template>
  <el-container class="layout">
    <el-aside :width="asideCollapsed ? '64px' : '200px'" class="aside">
      <div class="logo" @click="router.push('/dashboard')">
        <span v-if="!asideCollapsed">💪 智能健身系统</span>
        <span v-else>💪</span>
      </div>
      <el-menu :default-active="route.path" :collapse="asideCollapsed" router
        background-color="#1a1a2e" text-color="#bfcbd9" active-text-color="#409eff">
        <el-menu-item index="/dashboard"><el-icon><DataAnalysis /></el-icon><span>首页仪表盘</span></el-menu-item>
        <el-sub-menu index="/fitness">
          <template #title><el-icon><VideoCamera /></el-icon><span>健身动作分析</span></template>
          <el-menu-item index="/fitness/image"><el-icon><Picture /></el-icon><span>图片分析</span></el-menu-item>
          <el-menu-item index="/fitness/video"><el-icon><VideoPlay /></el-icon><span>视频分析</span></el-menu-item>
          <el-menu-item index="/fitness/camera"><el-icon><Camera /></el-icon><span>实时摄像头</span></el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="/health">
          <template #title><el-icon><Notebook /></el-icon><span>健康管理</span></template>
          <el-menu-item index="/health/plans"><el-icon><Tickets /></el-icon><span>健身+饮食计划</span></el-menu-item>
          <el-menu-item index="/health/weight"><el-icon><TrendCharts /></el-icon><span>体重记录</span></el-menu-item>
          <el-menu-item index="/health/food"><el-icon><DishDot /></el-icon><span>食物分析</span></el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/records"><el-icon><List /></el-icon><span>历史记录</span></el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <el-button text @click="asideCollapsed = !asideCollapsed">
          <el-icon :size="20"><Fold v-if="!asideCollapsed" /><Expand v-else /></el-icon>
        </el-button>
        <span class="header-title">{{ route.meta.title || '' }}</span>
        <div class="header-right">
          <span class="nickname">{{ auth.user?.nickname || auth.user?.username || '' }}</span>
          <el-button type="danger" text @click="handleLogout">退出</el-button>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const asideCollapsed = ref(false)

onMounted(async () => {
  if (!auth.isLoggedIn) {
    router.replace('/login')
    return
  }
  await auth.fetchProfile()
})

function handleLogout() {
  auth.logout()
  router.replace('/login')
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.aside { background: #1a1a2e; overflow-y: auto; }
.logo { height: 56px; display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 16px; font-weight: bold; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.1); }
.header { display: flex; align-items: center; gap: 12px; background: #fff; border-bottom: 1px solid #e4e7ed; padding: 0 20px; }
.header-title { font-size: 16px; color: #303133; }
.header-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.nickname { color: #606266; font-size: 14px; }
</style>
