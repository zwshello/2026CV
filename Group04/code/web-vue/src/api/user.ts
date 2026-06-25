import api from './index'

export const login = (username: string, password: string) =>
  api.post('/auth/login', { username, password })

export const register = (data: any) =>
  api.post('/auth/register', data)

export const getProfile = () =>
  api.get('/auth/profile')

export const updateProfile = (data: any) =>
  api.put('/auth/profile', data)
