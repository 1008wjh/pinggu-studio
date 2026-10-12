import client from './client'
export interface StudioResult { status: string; report?: string; answer?: string; sources?: string[]; operation?: string; source_files?: string[]; project_id?: string }
export const studioApi = {
  qa: (message: string) => client.post<StudioResult>('/studio/qa', { message }),
  review: (project_id: string, decision: 'approved'|'revision_required'|'rejected', comment = '') => client.post('/studio/review', { project_id, decision, comment }),
  land: (files: File[], instruction = '') => upload('/studio/land-assessment', files, instruction),
}
function upload(path: string, files: File[], instruction: string) {
  const form = new FormData()
  files.forEach(file => form.append('files', file))
  form.append('instruction', instruction)
  return client.post<StudioResult>(path, form, { headers: { 'Content-Type': 'multipart/form-data' } })
}

