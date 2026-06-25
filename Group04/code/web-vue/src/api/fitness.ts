import api from './index'

export const getExercises = () =>
  api.get('/exercises')

export const uploadImage = (file: File, exerciseType: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('exercise_type', exerciseType)
  return api.post('/fitness/image', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 })
}

export const uploadVideo = (file: File, exerciseType: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('exercise_type', exerciseType)
  return api.post('/fitness/video', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 })
}

export const startCameraSession = (exerciseType: string) =>
  api.post('/camera/start', { exercise_type: exerciseType })

export const sendCameraFrame = (file: File, sessionId: number) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('session_id', String(sessionId))
  return api.post('/camera/frame', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 10000 })
}

export const sendCameraSnapshot = (file: File, sessionId: number) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('session_id', String(sessionId))
  return api.post('/camera/snapshot', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 })
}

export const stopCameraSession = (sessionId: number) =>
  api.post('/camera/stop', { session_id: sessionId })

export const getImageRecords = (page = 1) =>
  api.get('/records/images', { params: { page } })

export const getVideoRecords = (page = 1) =>
  api.get('/records/videos', { params: { page } })

export const getVideoDetails = (recordId: number) =>
  api.get(`/records/videos/${recordId}/details`)

export const getCameraRecords = (page = 1) =>
  api.get('/records/camera', { params: { page } })
