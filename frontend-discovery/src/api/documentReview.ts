import client from './client'
export type ReviewAction = 'approve' | 'return' | 'edit'
export const documentReviewApi = {
  start: (form: FormData) => client.post('/document-review/workflows', form, { headers: { 'Content-Type': 'multipart/form-data' } }),
  get: (id: string) => client.get(`/document-review/workflows/${id}`),
  resume: (id: string, action: ReviewAction, comment = '') => client.post(`/document-review/workflows/${id}/resume`, { action, comment }),
}

