<template>
  <div class="page-container">
    <h2>🍎 食物识别分析</h2>
    <p class="desc">上传食物照片，AI 识别食物并分析营养成分</p>

    <div class="card-box mt-16">
      <el-row :gutter="20">
        <el-col :span="8">
          <el-upload :auto-upload="false" :show-file-list="false" :on-change="handleFileChange" accept="image/*" drag>
            <el-icon :size="40"><UploadFilled /></el-icon>
            <div>上传食物图片</div>
          </el-upload>
          <div v-if="loading" class="flex-center mt-16"><el-icon class="is-loading"><Loading /></el-icon> 识别中...</div>
        </el-col>
        <el-col :span="16">
          <div v-if="result" class="card-box">
            <img :src="previewUrl" style="width:100%; border-radius:8px; max-height:200px; object-fit:contain; background:#000" />
            <h3 class="mt-16">{{ result.food_name }}</h3>
            <el-row :gutter="12" class="mt-16">
              <el-col :span="6"><div class="nutrient"><div class="nv">{{ result.calories }}</div><div>卡路里 kcal</div></div></el-col>
              <el-col :span="6"><div class="nutrient"><div class="nv">{{ result.protein }}</div><div>蛋白质 g</div></div></el-col>
              <el-col :span="6"><div class="nutrient"><div class="nv">{{ result.carbs }}</div><div>碳水 g</div></div></el-col>
              <el-col :span="6"><div class="nutrient"><div class="nv">{{ result.fat }}</div><div>脂肪 g</div></div></el-col>
            </el-row>
            <div class="mt-16" style="color:#606266">{{ result.analysis }}</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <div class="card-box mt-16" v-if="history.length">
      <h3>📋 分析历史</h3>
      <el-table :data="history" class="mt-16">
        <el-table-column label="图片">
          <template #default="{ row }"><img :src="'/api/uploads/food/' + row.image_path.split('/').pop()" style="width:60px;height:60px;object-fit:cover;border-radius:6px" @error="(e:any)=>e.target.style.display='none'" /></template>
        </el-table-column>
        <el-table-column prop="food_name" label="食物" />
        <el-table-column prop="calories" label="热量(kcal)" />
        <el-table-column prop="protein" label="蛋白质(g)" />
        <el-table-column prop="carbs" label="碳水(g)" />
        <el-table-column prop="fat" label="脂肪(g)" />
        <el-table-column prop="created_at" label="时间" :formatter="(r:any)=>r.created_at?.slice(0,10)" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as healthApi from '@/api/health'

const loading = ref(false)
const previewUrl = ref('')
const result = ref<any>(null)
const history = ref<any[]>([])

onMounted(async () => {
  try { const r = await healthApi.getFoodRecords(); history.value = r.data || [] } catch { /* pass */ }
})

async function handleFileChange(uploadFile: any) {
  const file = uploadFile.raw as File
  previewUrl.value = URL.createObjectURL(file)
  loading.value = true
  result.value = null
  try {
    const res = await healthApi.analyzeFood(file)
    result.value = res.data
    ElMessage.success('识别完成')
    // 刷新历史
    try { const r = await healthApi.getFoodRecords(); history.value = r.data || [] } catch { /* pass */ }
  } catch (e: any) { ElMessage.error(e.message || '识别失败') }
  finally { loading.value = false }
}
</script>

<style scoped>
.desc { color: #909399; margin-top: 6px; font-size: 14px; }
.nutrient { text-align: center; padding: 12px; background: #f5f7fa; border-radius: 8px; }
.nv { font-size: 24px; font-weight: bold; color: #409eff; }
</style>
