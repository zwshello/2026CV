<template>
  <div class="page-container">
    <h2>🎬 视频动作分析</h2>
    <p class="desc">上传健身视频，系统逐帧分析动作并自动计数</p>

    <div class="card-box mt-16">
      <el-row :gutter="20" align="middle">
        <el-col :span="12">
          <el-select v-model="exerciseType" placeholder="选择动作类型" size="large" style="width:100%">
            <el-option v-for="ex in exercises" :key="ex.key" :label="`${ex.name} (${ex.name_en})`" :value="ex.key" />
          </el-select>
        </el-col>
        <el-col :span="12">
          <el-upload :auto-upload="false" :show-file-list="false" :on-change="handleFileChange" accept="video/*" drag>
            <el-icon :size="40"><VideoPlay /></el-icon>
            <div>拖拽或点击上传视频</div>
          </el-upload>
        </el-col>
      </el-row>

      <div v-if="loading" class="flex-center mt-16">
        <el-progress :percentage="progress" :stroke-width="14" style="width:400px" />
        <span style="margin-left:10px">分析中...</span>
      </div>

      <div v-if="result" class="mt-16">
        <el-row :gutter="16">
          <el-col :span="6"><div class="stat-card small"><div class="sl">总次数</div><div class="sv">{{ result.total_reps }}</div></div></el-col>
          <el-col :span="6"><div class="stat-card small green"><div class="sl">正确次数</div><div class="sv">{{ result.correct_reps }}</div></div></el-col>
          <el-col :span="6"><div class="stat-card small blue"><div class="sl">平均评分</div><div class="sv">{{ result.avg_score }}</div></div></el-col>
          <el-col :span="6"><div class="stat-card small orange"><div class="sl">时长(秒)</div><div class="sv">{{ result.duration_seconds }}</div></div></el-col>
        </el-row>

        <div class="card-box mt-16">
          <h4>📈 逐帧角度变化</h4>
          <div ref="chartRef" style="height:300px; width:100%"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { getExercises, uploadVideo } from '@/api/fitness'

const exercises = ref<any[]>([])
const exerciseType = ref('squat')
const loading = ref(false)
const progress = ref(0)
const result = ref<any>(null)
const chartRef = ref<HTMLElement | null>(null)

onMounted(async () => {
  try { const res = await getExercises(); exercises.value = res.data || [] } catch { /* pass */ }
})

async function handleFileChange(uploadFile: any) {
  const file = uploadFile.raw as File
  loading.value = true
  progress.value = 0
  result.value = null
  const timer = setInterval(() => { if (progress.value < 90) progress.value += 10 }, 500)

  try {
    const res = await uploadVideo(file, exerciseType.value)
    result.value = res.data
    progress.value = 100
    ElMessage.success('视频分析完成')
    await nextTick()
    renderChart()
  } catch (e: any) {
    ElMessage.error(e.message || '分析失败')
  } finally {
    clearInterval(timer)
    loading.value = false
  }
}

function renderChart() {
  if (!chartRef.value || !result.value?.frames_detail?.length) return
  const chart = echarts.init(chartRef.value)
  const frames = result.value.frames_detail as any[]
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: frames.map(f => f.frame), name: '帧' },
    yAxis: { type: 'value', name: '角度(°)' },
    series: [{
      data: frames.map(f => f.angle ?? null), type: 'line', smooth: true,
      lineStyle: { color: '#409eff' }, areaStyle: { color: 'rgba(64,158,255,0.1)' },
      markLine: { silent: true, data: [{ yAxis: 160, label: { formatter: '站立线' } }, { yAxis: 100, label: { formatter: '蹲下线' } }] },
    }],
  })
  window.addEventListener('resize', () => chart.resize())
}
</script>

<style scoped>
.desc { color: #909399; margin-top: 6px; font-size: 14px; }
.stat-card.small { padding: 16px; border-radius: 10px; color: #fff; background: linear-gradient(135deg, #667eea, #764ba2); }
.stat-card.green { background: linear-gradient(135deg, #43e97b, #38f9d7); }
.stat-card.blue { background: linear-gradient(135deg, #4facfe, #00f2fe); }
.stat-card.orange { background: linear-gradient(135deg, #fa709a, #fee140); }
.sl { font-size: 13px; opacity: 0.85; } .sv { font-size: 28px; font-weight: bold; }
</style>
