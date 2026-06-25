<template>
  <div class="page-container">
    <h2>📋 健身+饮食计划</h2>
    <el-tabs v-model="activeTab" class="mt-16">
      <el-tab-pane label="🏋️ 健身计划" name="fitness" />
      <el-tab-pane label="🍽️ 饮食计划" name="diet" />
      <el-tab-pane label="💪 锻炼计划" name="exercise" />
    </el-tabs>

    <!-- 健身计划 -->
    <div v-if="activeTab === 'fitness'">
      <el-button type="primary" @click="showFitnessDialog(null)">+ 创建健身计划</el-button>
      <div v-for="p in fitnessPlans" :key="p.id" class="card-box mt-16">
        <div class="flex-between">
          <div>
            <h4>{{ p.plan_name }}</h4>
            <span style="color:#909399;font-size:13px">{{ p.start_date }} ~ {{ p.end_date }} | 每周 {{ p.weekly_frequency }} 次</span>
            <div v-if="p.goal" class="mt-16">🎯 目标: {{ p.goal }}</div>
            <div v-if="p.target_weight">⚖️ 目标体重: {{ p.target_weight }} kg</div>
            <el-tag :type="p.status === 'active' ? 'success' : p.status === 'paused' ? 'warning' : 'info'" size="small">{{ {'active':'进行中','paused':'暂停','completed':'已完成'}[p.status] }}</el-tag>
          </div>
          <div>
            <el-button size="small" @click="showFitnessDialog(p)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteFitness(p.id)">删除</el-button>
          </div>
        </div>
      </div>

      <el-dialog v-model="fitnessDialogVisible" title="健身计划" width="500px">
        <el-form :model="fitnessForm" label-width="100px">
          <el-form-item label="计划名称"><el-input v-model="fitnessForm.plan_name" /></el-form-item>
          <el-form-item label="健身目标"><el-input v-model="fitnessForm.goal" /></el-form-item>
          <el-form-item label="目标体重"><el-input-number v-model="fitnessForm.target_weight" :min="30" :max="200" step="0.1" /> kg</el-form-item>
          <el-form-item label="开始日期"><el-date-picker v-model="fitnessForm.start_date" type="date" /></el-form-item>
          <el-form-item label="结束日期"><el-date-picker v-model="fitnessForm.end_date" type="date" /></el-form-item>
          <el-form-item label="每周频率"><el-input-number v-model="fitnessForm.weekly_frequency" :min="1" :max="7" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="fitnessForm.notes" type="textarea" /></el-form-item>
        </el-form>
        <template #footer><el-button type="primary" @click="handleSaveFitness">保存</el-button></template>
      </el-dialog>
    </div>

    <!-- 饮食计划 -->
    <div v-if="activeTab === 'diet'">
      <el-button type="primary" @click="showDietDialog(null)">+ 创建饮食计划</el-button>
      <el-table :data="dietPlans" class="mt-16">
        <el-table-column prop="plan_name" label="名称" />
        <el-table-column prop="daily_calorie_target" label="卡路里目标" />
        <el-table-column prop="protein_target" label="蛋白质(g)" />
        <el-table-column prop="carbs_target" label="碳水(g)" />
        <el-table-column prop="fat_target" label="脂肪(g)" />
        <el-table-column prop="date" label="日期" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" @click="showDietDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteDiet(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-dialog v-model="dietDialogVisible" title="饮食计划" width="500px">
        <el-form :model="dietForm" label-width="110px">
          <el-form-item label="计划名称"><el-input v-model="dietForm.plan_name" /></el-form-item>
          <el-form-item label="饮食内容"><el-input v-model="dietForm.content" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="卡路里目标"><el-input-number v-model="dietForm.daily_calorie_target" :min="500" :max="5000" /> kcal</el-form-item>
          <el-form-item label="蛋白质"><el-input-number v-model="dietForm.protein_target" :min="0" :max="500" step="0.1" /> g</el-form-item>
          <el-form-item label="碳水"><el-input-number v-model="dietForm.carbs_target" :min="0" :max="500" step="0.1" /> g</el-form-item>
          <el-form-item label="脂肪"><el-input-number v-model="dietForm.fat_target" :min="0" :max="200" step="0.1" /> g</el-form-item>
          <el-form-item label="日期"><el-date-picker v-model="dietForm.date" type="date" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="dietForm.notes" type="textarea" /></el-form-item>
        </el-form>
        <template #footer><el-button type="primary" @click="handleSaveDiet">保存</el-button></template>
      </el-dialog>
    </div>

    <!-- 锻炼计划 -->
    <div v-if="activeTab === 'exercise'">
      <el-button type="primary" @click="showExerciseDialog">+ 添加锻炼</el-button>
      <el-table :data="exercisePlans" class="mt-16">
        <el-table-column prop="exercise_name" label="动作" />
        <el-table-column prop="sets" label="组数" />
        <el-table-column prop="reps" label="次数" />
        <el-table-column prop="duration_minutes" label="时长(分)" />
        <el-table-column prop="rest_seconds" label="休息(秒)" />
        <el-table-column prop="day_of_week" label="星期" :formatter="(r: any) => ['','一','二','三','四','五','六','日'][r.day_of_week]" />
        <el-table-column prop="notes" label="备注" />
      </el-table>

      <el-dialog v-model="exerciseDialogVisible" title="添加锻炼" width="400px">
        <el-form :model="exerciseForm" label-width="80px">
          <el-form-item label="动作"><el-input v-model="exerciseForm.exercise_name" /></el-form-item>
          <el-form-item label="组数"><el-input-number v-model="exerciseForm.sets" :min="1" :max="10" /></el-form-item>
          <el-form-item label="次数"><el-input-number v-model="exerciseForm.reps" :min="1" :max="100" /></el-form-item>
          <el-form-item label="时长(分)"><el-input-number v-model="exerciseForm.duration_minutes" :min="0" :max="120" /></el-form-item>
          <el-form-item label="休息(秒)"><el-input-number v-model="exerciseForm.rest_seconds" :min="0" :max="300" /></el-form-item>
          <el-form-item label="星期"><el-select v-model="exerciseForm.day_of_week"><el-option v-for="i in 7" :key="i" :label="'周'+['','一','二','三','四','五','六','日'][i]" :value="i" /></el-select></el-form-item>
          <el-form-item label="备注"><el-input v-model="exerciseForm.notes" /></el-form-item>
        </el-form>
        <template #footer><el-button type="primary" @click="handleSaveExercise">保存</el-button></template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as healthApi from '@/api/health'

const activeTab = ref('fitness')

// 健身计划
const fitnessPlans = ref<any[]>([])
const fitnessDialogVisible = ref(false)
const editingFitnessId = ref<number | null>(null)
const fitnessForm = reactive({ plan_name: '', goal: '', target_weight: null as any, start_date: '', end_date: '', weekly_frequency: 3, notes: '' })

function showFitnessDialog(item: any) {
  editingFitnessId.value = item?.id || null
  Object.assign(fitnessForm, { plan_name: '', goal: '', target_weight: null, start_date: '', end_date: '', weekly_frequency: 3, notes: '', ...item })
  fitnessDialogVisible.value = true
}
async function handleSaveFitness() {
  try {
    const data = { ...fitnessForm }
    data.start_date = typeof data.start_date === 'string' ? data.start_date : new Date(data.start_date).toISOString().slice(0, 10)
    data.end_date = typeof data.end_date === 'string' ? data.end_date : new Date(data.end_date).toISOString().slice(0, 10)
    if (editingFitnessId.value) await healthApi.updateFitnessPlan(editingFitnessId.value, data)
    else await healthApi.createFitnessPlan(data)
    fitnessDialogVisible.value = false
    await loadFitness()
    ElMessage.success('保存成功')
  } catch (e: any) { ElMessage.error(e.message || '失败') }
}
async function handleDeleteFitness(id: number) {
  await ElMessageBox.confirm('确定删除？', '提示', { type: 'warning' })
  await healthApi.deleteFitnessPlan(id)
  await loadFitness()
  ElMessage.success('已删除')
}

// 饮食计划
const dietPlans = ref<any[]>([])
const dietDialogVisible = ref(false)
const editingDietId = ref<number | null>(null)
const dietForm = reactive({ plan_name: '', content: '', daily_calorie_target: 2000, protein_target: 80, carbs_target: 250, fat_target: 65, date: '', notes: '' })

function showDietDialog(item: any) {
  editingDietId.value = item?.id || null
  Object.assign(dietForm, { plan_name: '', content: '', daily_calorie_target: 2000, protein_target: 80, carbs_target: 250, fat_target: 65, date: '', notes: '', ...item })
  dietDialogVisible.value = true
}
async function handleSaveDiet() {
  const data = { ...dietForm }
  data.date = typeof data.date === 'string' ? data.date : new Date(data.date || Date.now()).toISOString().slice(0, 10)
  try {
    if (editingDietId.value) await healthApi.updateDietPlan(editingDietId.value, data)
    else await healthApi.createDietPlan(data)
    dietDialogVisible.value = false
    await loadDiet()
    ElMessage.success('保存成功')
  } catch (e: any) { ElMessage.error(e.message || '失败') }
}
async function handleDeleteDiet(id: number) {
  await ElMessageBox.confirm('确定删除？', '提示', { type: 'warning' })
  await healthApi.deleteDietPlan(id)
  await loadDiet()
  ElMessage.success('已删除')
}

// 锻炼计划
const exercisePlans = ref<any[]>([])
const exerciseDialogVisible = ref(false)
const exerciseForm = reactive({ exercise_name: '', sets: 3, reps: 12, duration_minutes: null as any, rest_seconds: 60, day_of_week: null as any, content: '', notes: '' })

function showExerciseDialog() { exerciseDialogVisible.value = true }
async function handleSaveExercise() {
  try {
    await healthApi.createExercisePlan(exerciseForm)
    exerciseDialogVisible.value = false
    await loadExercise()
    ElMessage.success('添加成功')
  } catch (e: any) { ElMessage.error(e.message || '失败') }
}

async function loadFitness() { try { const r = await healthApi.getFitnessPlans(); fitnessPlans.value = r.data || [] } catch { /* pass */ } }
async function loadDiet() { try { const r = await healthApi.getDietPlans(); dietPlans.value = r.data || [] } catch { /* pass */ } }
async function loadExercise() { try { const r = await healthApi.getExercisePlans(); exercisePlans.value = r.data || [] } catch { /* pass */ } }

onMounted(() => { loadFitness(); loadDiet(); loadExercise() })
</script>
