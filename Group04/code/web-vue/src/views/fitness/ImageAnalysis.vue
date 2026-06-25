<template>
  <div class="page-container">
    <h2>📸 图片动作分析</h2>
    <p class="desc">上传健身动作图片，YOLO 姿态估计 + Qwen-VL 大模型智能分析动作规范性</p>

    <div class="card-box mt-16">
      <el-row :gutter="20" align="middle">
        <el-col :span="12">
          <el-select v-model="exerciseType" placeholder="选择动作类型" size="large" style="width:100%">
            <el-option v-for="ex in exercises" :key="ex.key" :label="`${ex.name} (${ex.name_en})`" :value="ex.key" />
          </el-select>
        </el-col>
        <el-col :span="12">
          <el-upload :auto-upload="false" :show-file-list="false" :on-change="handleFileChange" accept="image/*" drag>
            <el-icon :size="40"><UploadFilled /></el-icon>
            <div>拖拽或点击上传图片</div>
          </el-upload>
        </el-col>
      </el-row>

      <div v-if="loading" class="flex-center mt-16"><el-icon class="is-loading" :size="30"><Loading /></el-icon><span style="margin-left:10px">分析中...</span></div>

      <div v-if="result" class="mt-16">
        <el-row :gutter="20">
          <el-col :span="12">
            <h4>上传图片</h4>
            <img :src="previewUrl" style="width:100%; border-radius:8px; max-height:400px; object-fit:contain; background:#000" />
          </el-col>
          <el-col :span="12">
            <div class="card-box">
              <h4>🤖 AI 分析结果</h4>
              <el-tag :type="result.ai?.is_correct ? 'success' : 'danger'" size="large" class="mt-16">
                {{ result.ai?.is_correct ? '✅ 动作规范' : '⚠️ 需要改进' }}
              </el-tag>
              <div class="mt-16"><strong>评分：</strong><span style="font-size:24px;color:#409eff">{{ result.ai?.score || '-' }}</span> / 100</div>
              <div class="mt-16"><strong>检测角度：</strong>{{ result.pose?.angle || '-' }}°</div>
              <div class="mt-16"><strong>状态：</strong>{{ result.pose?.phase || '-' }}</div>
              <div v-if="result.ai?.errors?.length" class="mt-16">
                <strong>存在问题：</strong>
                <ul><li v-for="e in result.ai.errors" :key="e">{{ e }}</li></ul>
              </div>
              <div v-if="result.ai?.suggestions?.length" class="mt-16">
                <strong>改进建议：</strong>
                <ul><li v-for="s in result.ai.suggestions" :key="s">{{ s }}</li></ul>
              </div>
              <div class="mt-16" style="color:#909399;font-size:13px">{{ result.ai?.analysis_text }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getExercises, uploadImage } from '@/api/fitness'

const exercises = ref<any[]>([])
const exerciseType = ref('squat')
const loading = ref(false)
const previewUrl = ref('')
const result = ref<any>(null)

onMounted(async () => {
  try { const res = await getExercises(); exercises.value = res.data || [] } catch { /* pass */ }
})

async function handleFileChange(uploadFile: any) {
  const file = uploadFile.raw as File
  previewUrl.value = URL.createObjectURL(file)
  loading.value = true
  result.value = null
  try {
    const res = await uploadImage(file, exerciseType.value)
    result.value = res.data
    ElMessage.success('分析完成')
  } catch (e: any) {
    ElMessage.error(e.message || '分析失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.desc { color: #909399; margin-top: 6px; font-size: 14px; }
</style>
