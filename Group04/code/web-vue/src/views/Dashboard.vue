<template>
  <div class="page-container">
    <h2>📊 仪表盘</h2>
    <el-row :gutter="20" class="mt-16">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <div class="stat-card">
          <div class="stat-label">{{ stat.label }}</div>
          <div class="stat-value">{{ stat.value }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="mt-16">
      <el-col :span="12">
        <div class="card-box">
          <h3>🏋️ 快捷入口</h3>
          <el-row :gutter="12" class="mt-16">
            <el-col :span="8" v-for="entry in quickEntries" :key="entry.path">
              <div class="quick-card" @click="router.push(entry.path)">
                <span class="quick-icon">{{ entry.icon }}</span>
                <div class="quick-label">{{ entry.label }}</div>
              </div>
            </el-col>
          </el-row>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="card-box">
          <h3>📋 支持的健身动作</h3>
          <el-table :data="exercises" size="small" class="mt-16" max-height="260">
            <el-table-column prop="key" label="动作" width="120" />
            <el-table-column prop="name" label="名称" width="100" />
            <el-table-column prop="description" label="说明" show-overflow-tooltip />
          </el-table>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getExercises } from '@/api/fitness'
import { getFitnessPlans, getWeightRecords } from '@/api/health'

const router = useRouter()
const exercises = ref<any[]>([])
const stats = ref([
  { label: '健身计划', value: '0' },
  { label: '分析记录', value: '0' },
  { label: '体重记录', value: '0' },
  { label: '支持动作', value: '7' },
])

const quickEntries = [
  { icon: '📸', label: '图片分析', path: '/fitness/image' },
  { icon: '🎬', label: '视频分析', path: '/fitness/video' },
  { icon: '📷', label: '实时摄像头', path: '/fitness/camera' },
  { icon: '📋', label: '健身计划', path: '/health/plans' },
  { icon: '🍎', label: '食物分析', path: '/health/food' },
  { icon: '📊', label: '历史记录', path: '/records' },
]

onMounted(async () => {
  try {
    const [ex, plans, weights] = await Promise.all([
      getExercises(),
      getFitnessPlans(),
      getWeightRecords(),
    ])
    exercises.value = ex.data || []
    stats.value[0].value = String((plans.data || []).length)
    stats.value[2].value = String((weights.data || []).length)
  } catch { /* pass */ }
})
</script>

<style scoped>
.stat-card { background: linear-gradient(135deg, #667eea, #764ba2); border-radius: 12px; padding: 24px; color: #fff; }
.stat-label { font-size: 14px; opacity: 0.85; }
.stat-value { font-size: 32px; font-weight: bold; margin-top: 8px; }
.quick-card { text-align: center; padding: 16px; border: 1px solid #e4e7ed; border-radius: 10px; cursor: pointer; transition: all 0.2s; }
.quick-card:hover { border-color: #409eff; background: #ecf5ff; }
.quick-icon { font-size: 28px; }
.quick-label { font-size: 13px; margin-top: 6px; color: #606266; }
</style>
