<template>
  <div class="page-container">
    <h2>⚖️ 体重记录</h2>
    <div class="card-box mt-16">
      <el-row :gutter="20">
        <el-col :span="8">
          <h4>记录体重</h4>
          <el-form class="mt-16">
            <el-form-item label="体重(kg)"><el-input-number v-model="form.weight" :min="30" :max="200" step="0.1" /></el-form-item>
            <el-form-item label="体脂率(%)"><el-input-number v-model="form.body_fat_pct" :min="1" :max="60" step="0.1" /></el-form-item>
            <el-form-item label="日期"><el-date-picker v-model="form.record_date" type="date" /></el-form-item>
            <el-form-item label="备注"><el-input v-model="form.notes" /></el-form-item>
            <el-button type="primary" @click="handleSave">记录</el-button>
          </el-form>
        </el-col>
        <el-col :span="16">
          <div ref="chartRef" style="height:350px; width:100%"></div>
        </el-col>
      </el-row>

      <el-table :data="records" class="mt-16">
        <el-table-column prop="record_date" label="日期" />
        <el-table-column prop="weight" label="体重(kg)" />
        <el-table-column prop="body_fat_pct" label="体脂(%)" />
        <el-table-column prop="notes" label="备注" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import * as healthApi from '@/api/health'

const records = ref<any[]>([])
const chartRef = ref<HTMLElement | null>(null)
const form = reactive({ weight: 70, body_fat_pct: null as any, record_date: new Date(), notes: '' })

onMounted(() => loadRecords())

async function loadRecords() {
  try { const r = await healthApi.getWeightRecords(); records.value = r.data || []; await nextTick(); renderChart() } catch { /* pass */ }
}
async function handleSave() {
  try {
    const data = { ...form, record_date: new Date(form.record_date).toISOString().slice(0, 10) }
    await healthApi.createWeightRecord(data)
    ElMessage.success('记录成功')
    await loadRecords()
  } catch (e: any) { ElMessage.error(e.message || '失败') }
}
function renderChart() {
  if (!chartRef.value || !records.value.length) return
  const chart = echarts.init(chartRef.value)
  const reversed = [...records.value].reverse()
  chart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: reversed.map(r => r.record_date) },
    yAxis: { type: 'value', name: 'kg' },
    series: [{ data: reversed.map(r => r.weight), type: 'line', smooth: true, areaStyle: { color: 'rgba(64,158,255,0.2)' } }],
  })
}
</script>
