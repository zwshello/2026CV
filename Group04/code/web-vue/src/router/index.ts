import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { noAuth: true },
    },
    {
      path: '/',
      component: () => import('@/views/Layout.vue'),
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard.vue'), meta: { title: '首页' } },
        { path: 'fitness/image', name: 'ImageAnalysis', component: () => import('@/views/fitness/ImageAnalysis.vue'), meta: { title: '图片分析' } },
        { path: 'fitness/video', name: 'VideoAnalysis', component: () => import('@/views/fitness/VideoAnalysis.vue'), meta: { title: '视频分析' } },
        { path: 'fitness/camera', name: 'CameraDetection', component: () => import('@/views/fitness/CameraDetection.vue'), meta: { title: '实时摄像头' } },
        { path: 'health/plans', name: 'HealthPlans', component: () => import('@/views/health/HealthPlans.vue'), meta: { title: '健身计划' } },
        { path: 'health/weight', name: 'WeightTracking', component: () => import('@/views/health/WeightTracking.vue'), meta: { title: '体重记录' } },
        { path: 'health/food', name: 'FoodAnalysis', component: () => import('@/views/health/FoodAnalysis.vue'), meta: { title: '食物分析' } },
        { path: 'records', name: 'Records', component: () => import('@/views/Records.vue'), meta: { title: '历史记录' } },
      ],
    },
  ],
})

export default router
