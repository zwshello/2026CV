import api from './index'

// 健身计划
export const getFitnessPlans = () => api.get('/plans/fitness')
export const createFitnessPlan = (data: any) => api.post('/plans/fitness', data)
export const updateFitnessPlan = (id: number, data: any) => api.put(`/plans/fitness/${id}`, data)
export const deleteFitnessPlan = (id: number) => api.delete(`/plans/fitness/${id}`)

// 饮食计划
export const getDietPlans = () => api.get('/plans/diet')
export const createDietPlan = (data: any) => api.post('/plans/diet', data)
export const updateDietPlan = (id: number, data: any) => api.put(`/plans/diet/${id}`, data)
export const deleteDietPlan = (id: number) => api.delete(`/plans/diet/${id}`)

// 锻炼计划
export const getExercisePlans = (fitnessPlanId?: number) =>
  api.get('/plans/exercise', { params: fitnessPlanId ? { fitness_plan_id: fitnessPlanId } : {} })
export const createExercisePlan = (data: any) => api.post('/plans/exercise', data)

// 体重
export const getWeightRecords = () => api.get('/weight')
export const createWeightRecord = (data: any) => api.post('/weight', data)

// 食物分析
export const analyzeFood = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/food/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 })
}
export const getFoodRecords = () => api.get('/food/records')
