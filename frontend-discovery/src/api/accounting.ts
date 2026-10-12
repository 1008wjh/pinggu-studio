import client from './client'

export type AccountingAction = 'approve' | 'edit' | 'return'
export interface AccountingReview { workflow_id?: string; step?: string; status?: string; confidence?: number; risk?: number; original_data?: Record<string, unknown>; ai_output?: Record<string, unknown>; display_data?: Record<string, unknown>; rules?: string }
export interface AccountingWorkflow { workflow_id: string; status: string; current_step: string; confidence: number; risk: number; review: AccountingReview; step_outputs: Record<string, Record<string, unknown>>; reviews: any[]; audit_logs: any[]; checkpoint_version: number }
export interface AccountingWorkflowListItem { id: string; status: string; current_step: string; checkpoint_version: number; created_at?: string; updated_at?: string }
export const accountingApi = {
  start: (form: FormData) => client.post<AccountingWorkflow>('/document-review/workflows', form, { headers: { 'Content-Type': 'multipart/form-data' } }),
  list: () => client.get<{ items: AccountingWorkflowListItem[] }>('/document-review/workflows'),
  discard: (id: string) => client.delete<{ deleted: boolean }>(`/document-review/workflows/${id}`),
  get: (id: string) => client.get<AccountingWorkflow>(`/document-review/workflows/${id}`),
  resume: (id: string, action: AccountingAction, edited_data: Record<string, unknown> = {}, comment = '') => client.post<AccountingWorkflow>(`/document-review/workflows/${id}/resume`, { action, edited_data, comment }),
  downloadReport: (id: string, key: string) => client.get(`/document-review/workflows/${id}/reports/${key}`, { responseType: 'blob' }),
  downloadTable: (id: string, key: string) => client.get(`/document-review/workflows/${id}/tables/${key}`, { responseType: 'blob' }),
  uploadTable: (id: string, file: File) => { const form = new FormData(); form.append('table_file', file); return client.post<AccountingWorkflow>(`/document-review/workflows/${id}/table-upload`, form, { headers: { 'Content-Type': 'multipart/form-data' } }) },
}

