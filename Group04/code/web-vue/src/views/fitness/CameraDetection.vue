<template>
  <div class="page-container">
    <h2>📷 实时摄像头检测</h2>
    <p class="desc">打开摄像头，实时检测健身动作并计数</p>

    <div class="card-box mt-16">
      <el-row :gutter="20" align="middle">
        <el-col :span="8">
          <el-select v-model="exerciseType" placeholder="选择动作" size="large" style="width:100%">
            <el-option v-for="ex in exercises" :key="ex.key" :label="`${ex.name}`" :value="ex.key" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-button :type="sessionActive ? 'danger' : 'primary'" size="large" @click="toggleSession" :disabled="!exerciseType">
            {{ sessionActive ? '停止检测' : '开始检测' }}
          </el-button>
        </el-col>
        <el-col :span="8">
          <el-button size="large" :disabled="!sessionActive" @click="takeSnapshot">📸 截图并 AI 分析</el-button>
        </el-col>
      </el-row>

      <div class="mt-16" v-if="sessionActive">
        <el-row :gutter="16">
          <el-col :span="16">
            <video ref="videoRef" autoplay playsinline style="width:100%; border-radius:8px; background:#000; max-height:400px" />
            <canvas ref="canvasRef" style="display:none" />
          </el-col>
          <el-col :span="8">
            <div class="result-panel">
              <div class="big-count">{{ repCount }}</div>
              <div style="font-size:14px;color:#909399">完成次数</div>
              <el-divider />
              <div><strong>当前角度：</strong>{{ currentAngle || '-' }}°</div>
              <div><strong>动作阶段：</strong>{{ currentPhase }}</div>
              <div><strong>动作：</strong>{{ exerciseName }}</div>
              <el-divider />
              <div v-if="lastActionCompleted" style="color:#67c23a;font-size:16px">✅ 完成一次！</div>
            </div>
          </el-col>
        </el-row>
      </div>

      <!-- AI 分析对话框 -->
      <el-dialog v-model="snapshotVisible" title="AI 动作分析" width="600px">
        <div v-if="snapshotLoading" class="text-center"><el-icon class="is-loading" :size="30"><Loading /></el-icon> 分析中...</div>
        <div v-else-if="snapshotResult">
          <img :src="snapshotUrl" style="width:100%; border-radius:8px; max-height:300px; object-fit:contain; background:#000" />
          <div class="mt-16"><strong>评分：</strong>{{ snapshotResult.ai?.score || '-' }} / 100</div>
          <div class="mt-16"><strong>分析：</strong>{{ snapshotResult.ai?.analysis_text }}</div>
          <div v-if="snapshotResult.ai?.suggestions?.length" class="mt-16">
            <strong>建议：</strong>
            <ul><li v-for="s in snapshotResult.ai.suggestions" :key="s">{{ s }}</li></ul>
          </div>
        </div>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getExercises, startCameraSession, sendCameraFrame, sendCameraSnapshot, stopCameraSession } from '@/api/fitness'

const exercises = ref<any[]>([])
const exerciseType = ref('squat')
const exerciseName = ref('')
const sessionActive = ref(false)
const sessionId = ref<number | null>(null)
const repCount = ref(0)
const currentAngle = ref<number | null>(null)
const currentPhase = ref('standby')
const lastActionCompleted = ref(false)

const videoRef = ref<HTMLVideoElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
let stream: MediaStream | null = null
let frameTimer: number | null = null

const snapshotVisible = ref(false)
const snapshotLoading = ref(false)
const snapshotUrl = ref('')
const snapshotResult = ref<any>(null)

onMounted(async () => {
  try { const res = await getExercises(); exercises.value = res.data || [] } catch { /* pass */ }
})

onUnmounted(() => { stopCamera(); })

async function toggleSession() {
  if (sessionActive.value) {
    await stopCamera()
  } else {
    await startCamera()
  }
}

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' } })
    if (videoRef.value) videoRef.value.srcObject = stream

    const res = await startCameraSession(exerciseType.value)
    sessionId.value = res.data.session_id
    exerciseName.value = res.data.exercise_name || exerciseType.value
    sessionActive.value = true
    repCount.value = 0
    ElMessage.success('摄像头会话已开始')

    // 每隔 1 秒发送帧进行分析
    frameTimer = window.setInterval(sendFrame, 1000)
  } catch (e: any) {
    ElMessage.error('无法打开摄像头: ' + (e.message || '未知错误'))
  }
}

function sendFrame() {
  if (!canvasRef.value || !videoRef.value || !sessionId.value) return
  const canvas = canvasRef.value
  canvas.width = 640
  canvas.height = 480
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(videoRef.value, 0, 0, 640, 480)
  canvas.toBlob(async (blob) => {
    if (!blob) return
    try {
      const file = new File([blob], 'frame.jpg', { type: 'image/jpeg' })
      const res = await sendCameraFrame(file, sessionId.value!)
      repCount.value = res.data.rep_count
      currentAngle.value = res.data.angle
      currentPhase.value = res.data.phase
      if (res.data.action_completed) {
        lastActionCompleted.value = true
        setTimeout(() => lastActionCompleted.value = false, 2000)
      }
    } catch { /* pass */ }
  }, 'image/jpeg', 0.7)
}

async function takeSnapshot() {
  if (!canvasRef.value || !videoRef.value || !sessionId.value) return
  const canvas = canvasRef.value
  canvas.width = 640; canvas.height = 480
  canvas.getContext('2d')?.drawImage(videoRef.value, 0, 0, 640, 480)

  snapshotUrl.value = canvas.toDataURL('image/jpeg')
  snapshotVisible.value = true
  snapshotLoading.value = true
  snapshotResult.value = null

  canvas.toBlob(async (blob) => {
    if (!blob) return
    try {
      const file = new File([blob], 'snapshot.jpg', { type: 'image/jpeg' })
      const res = await sendCameraSnapshot(file, sessionId.value!)
      snapshotResult.value = res.data
    } catch { /* pass */ }
    snapshotLoading.value = false
  }, 'image/jpeg', 0.8)
}

async function stopCamera() {
  if (frameTimer) { clearInterval(frameTimer); frameTimer = null }
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  if (sessionId.value) {
    try { await stopCameraSession(sessionId.value) } catch { /* pass */ }
  }
  sessionActive.value = false
  sessionId.value = null
  ElMessage.info('检测已停止')
}
</script>

<style scoped>
.desc { color: #909399; margin-top: 6px; font-size: 14px; }
.result-panel { background: #f8f9fb; border-radius: 10px; padding: 20px; text-align: center; }
.big-count { font-size: 56px; font-weight: bold; color: #409eff; }
</style>
