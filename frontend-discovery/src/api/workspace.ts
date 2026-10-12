import client from './client'

export interface WorkspaceSheet {
  name: string
  headers: string[]
  rows: Array<Record<string, unknown>>
  row_count_preview?: number
}

export interface WorkspaceTableResult {
  file_name: string
  type: string
  sheets: WorkspaceSheet[]
}

export const workspaceApi = {
  extract: (file: File, maxRows?: number) => {
    const form = new FormData()
    form.append('file', file)
    return client.post('/workspace/extract', form, { params: { max_rows: maxRows }, headers: { 'Content-Type': 'multipart/form-data' } })
  },
  summarize: (file: File, maxRows?: number) => {
    const form = new FormData()
    form.append('file', file)
    return client.post<{ file_name: string; summary: string; source_type: string }>('/workspace/summarize', form, { params: { max_rows: maxRows }, headers: { 'Content-Type': 'multipart/form-data' } })
  },
  inspect: (file: File, maxRows = 20) => {
    const form = new FormData()
    form.append('file', file)
    return client.post<WorkspaceTableResult>('/workspace/spreadsheet/inspect', form, { params: { max_rows: maxRows }, headers: { 'Content-Type': 'multipart/form-data' } })
  },
  merge: (files: File[], sheetName = 'merged') => {
    const form = new FormData()
    files.forEach(file => form.append('files', file))
    return client.post<Blob>('/workspace/spreadsheet/merge', form, { params: { sheet_name: sheetName }, headers: { 'Content-Type': 'multipart/form-data' }, responseType: 'blob' })
  },
}

