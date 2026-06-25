<template>
  <div class="page-container">
    <h2>📊 历史记录</h2>
    <el-tabs v-model="activeTab" class="mt-16">
      <el-tab-pane label="📸 图片分析记录" name="images" />
      <el-tab-pane label="🎬 视频分析记录" name="videos" />
      <el-tab-pane label="📷 摄像头会话" name="camera" />
    </el-tabs>

    <!-- 图片记录 -->
    <el-table v-if="activeTab==='images'" :data="imageRecords" class="mt-16">
      <el-table-column prop="exercise_type" label="动作类型" />
      <el-table-column prop="score" label="评分" />
      <el-table-column prop="ai_analysis" label="AI 分析" show-overflow-tooltip />
      <el-table-column prop="created_at" label="时间" :formatter="(r:any)=>r.created_at?.slice(0,19)" />
    </el-table>

    <!-- 视频记录 -->
    <el-table v-if="activeTab==='videos'" :data="videoRecords" class="mt-16">
      <el-table-column prop="exercise_type" label="动作类型" />
      <el-table-column prop="total_reps" label="总次数" />
      <el-table-column prop="correct_reps" label="正确次数" />
      <el-table-column prop="avg_score" label="平均评分" />
      <el-table-column prop="duration_seconds" label="时长(秒)" />
      <el-table-column prop="created_at" label="时间" :formatter="(r:any)=>r.created_at?.slice(0,19)" />
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="showVideoDetail(row)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 摄像头记录 -->
    <el-table v-if="activeTab==='camera'" :data="cameraRecords" class="mt-16">
      <el-table-column prop="exercise_type" label="动作类型" />
      <el-table-column prop="total_reps" label="总次数" />
      <el-table-column prop="correct_reps" label="正确次数" />
      <el-table-column prop="avg_score" label="平均评分" />
      <el-table-column prop="duration_seconds" label="时长(秒)" />
      <el-table-column prop="session_start" label="开始时间" :formatter="(r:any)=>r.session_start?.slice(0,19)" />
      <el-table-column prop="status" label="状态">
        <template #default="{ row }"><el-tag :type="row.status==='completed'?'success':'info'">{{ row.status==='completed'?'已完成':'进行中' }}</el-tag></template>
      </el-table-column>
    </el-table>

    <el-pagination class="mt-16" v-if="activeTab !== 'camera'" layout="prev, pager, next" :total="total" :page-size="20" @current-change="changePage" />

    <!-- 视频详情对话框 -->
    <el-dialog v-model="detailVisible" title="视频逐帧分析详情" width="700px">
      <div ref="detailChartRef" style="height:300px; width:100%"></div>
      <el-table :data="detailAnalyses" max-height="400" class="mt-16" size="small">
        <el-table-column prop="frame_index" label="帧" width="70" />
        <el-table-column prop="rep_number" label="次数" width="60" />
        <el-table-column prop="action_phase" label="阶段" width="90" />
        <el-table-column prop="is_correct" label="正确" width="60">
          <template #default="{ row }"><el-tag :type="row.is_correct ? 'success' : 'danger'" size="small">{{ row.is_correct ? '✓' : '✗' }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="score" label="评分" width="60" />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import * as echarts from 'echarts'
import * as fitnessApi from '@/api/fitness'

const activeTab = ref('images')
const imageRecords = ref<any[]>([])
const videoRecords = ref<any[]>([])
const cameraRecords = ref<any[]>([])
const total = ref(0)
const page = ref(1)

const detailVisible = ref(false)
const detailAnalyses = ref<any[]>([])
const detailChartRef = ref<HTMLElement | null>(null)

async function loadImages(p = 1) {
  try { const r = await fitnessApi.getImageRecords(p); imageRecords.value = r.data.items; total.value = r.data.total } catch { /* pass */ }
}
async function loadVideos(p = 1) {
  try { const r = await fitnessApi.getVideoRecords(p); videoRecords.value = r.data.items; total.value = r.data.total } catch { /* pass */ }
}
async function loadCamera() {
  try { const r = await fitnessApi.getCameraRecords(); cameraRecords.value = r.data.items } catch { /* pass */ }
}
function changePage(p: number) { page.value = p; activeTab.value === 'images' ? loadImages(p) : loadVideos(p) }

async function showVideoDetail(row: any) {
  try {
    const r = await fitnessApi.getVideoDetails(row.id)
    detailAnalyses.value = r.data.analyses || []
    detailVisible.value = true
    await nextTick()
    if (detailChartRef.value && detailAnalyses.value.length) {
      const chart = echarts.init(detailChartRef.value)
      const idx = detailAnalyses.value.map(a => a.frame_index)
      const scores = detailAnalyses.value.map(a => a.score ?? 0)
      chart.setOption({
        tooltip: { trigger: 'axis' },
        xAxis: { type: 'category', data: idx },
        yAxis: { type: 'value', name: '评分' },
        series: [{ data: scores, type: 'bar', itemStyle: { color: '#409eff' } }],
      })
    }
  } catch { /* pass */ }
}

loadImages()
loadVideos()
loadCamera()
</script>
