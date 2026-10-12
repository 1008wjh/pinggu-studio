import client from './client'
export const evaluationApi = {
  tasks: () => client.get('/evaluation/tasks'),
  create: (form: FormData) => client.post('/evaluation/tasks', form, { headers: { 'Content-Type': 'multipart/form-data' } }),
  addSample: (id: string, data: Record<string, unknown>) => client.post(`/evaluation/tasks/${id}/samples`, data),
  addSampleWithAttachment: (id: string, form: FormData) => client.post(`/evaluation/tasks/${id}/samples/upload`, form, { headers: { 'Content-Type': 'multipart/form-data' } }),
  start: (id: string) => client.post(`/evaluation/tasks/${id}/start`),
  stop: (id: string) => client.post(`/evaluation/tasks/${id}/stop`),
  report: (id: string) => client.get(`/evaluation/tasks/${id}`),
  export: (id: string) => client.get(`/evaluation/tasks/${id}/export.csv`, { responseType: 'blob' }),
}
