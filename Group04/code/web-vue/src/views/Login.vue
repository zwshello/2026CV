<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="title">智能康复+健身辅助系统</h1>
      <p class="subtitle">基于 YOLO 姿态识别 + AI 大模型分析</p>
      <el-tabs v-model="tab" class="tabs">
        <el-tab-pane label="登录" name="login" />
        <el-tab-pane label="注册" name="register" />
      </el-tabs>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="0">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="用户名" size="large" prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item v-if="tab === 'register'" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" placeholder="确认密码" size="large" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-button type="primary" size="large" :loading="loading" class="submit-btn" @click="handleSubmit">
          {{ tab === 'login' ? '登 录' : '注 册' }}
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const tab = ref('login')
const loading = ref(false)
const formRef = ref()
const form = reactive({ username: '', password: '', confirmPassword: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少6位', trigger: 'blur' }],
  confirmPassword: [{
    validator: (_: any, v: string, cb: any) => {
      if (tab.value === 'register' && v !== form.password) cb(new Error('两次密码不一致'))
      else cb()
    }, trigger: 'blur'
  }],
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    if (tab.value === 'login') {
      await auth.login(form.username, form.password)
    } else {
      await auth.register({ username: form.username, password: form.password })
    }
    ElMessage.success(tab.value === 'login' ? '登录成功' : '注册成功')
    router.replace('/')
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); }
.login-card { width: 420px; padding: 40px; background: rgba(255,255,255,0.95); border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }
.title { text-align: center; font-size: 22px; color: #1a1a2e; margin-bottom: 6px; }
.subtitle { text-align: center; font-size: 13px; color: #909399; margin-bottom: 20px; }
.submit-btn { width: 100%; margin-top: 8px; }
</style>
