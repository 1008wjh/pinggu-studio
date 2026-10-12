import client from './client'
export interface KnowledgeAgent { key: string; name: string }
export interface KnowledgeBase { id: string; name: string; description: string; agents: KnowledgeAgent[]; document_count: number; milvus_partition: string; created_at: string }
export interface KnowledgeDocument { id: string; knowledge_base_id: string; title: string; source_name: string; file_type: string; status: string; chunk_count: number; vector_count: number; vector_error?: string; error_message?: string; created_at?: string }
export interface KnowledgeDocumentDetail extends KnowledgeDocument { chunks: Array<{ id: string; chunk_index: number; content: string; metadata: Record<string, unknown> }> }
export const knowledgeApi = {
  listBases: (page = 1, pageSize = 20) => client.get<{items: KnowledgeBase[]; page: number; page_size: number; total: number}>(`/knowledge/bases?page=${page}&page_size=${pageSize}`),
  createBase: (data: {name: string; description: string; agent_keys: string[]}) => client.post<KnowledgeBase>('/knowledge/bases', data),
  updateBase: (id: string, data: {name?: string; description?: string; agent_keys?: string[]}) => client.patch<KnowledgeBase>(`/knowledge/bases/${id}`, data),
  removeBase: (id: string) => client.delete(`/knowledge/bases/${id}`),
  listDocuments: (baseId: string) => client.get<{items: KnowledgeDocument[]}>(`/knowledge/bases/${baseId}/documents`),
  upload: (baseId: string, file: File, title = '') => { const form = new FormData(); form.append('file', file); form.append('title', title); return client.post<KnowledgeDocument>(`/knowledge/bases/${baseId}/documents`, form, {headers:{'Content-Type':'multipart/form-data'}}) },
  getDocument: (id: string) => client.get<KnowledgeDocumentDetail>(`/knowledge/documents/${id}`),
  updateDocument: (id: string, file: File, title = '') => { const form = new FormData(); form.append('file', file); form.append('title', title); return client.put<KnowledgeDocument>(`/knowledge/documents/${id}`, form, {headers:{'Content-Type':'multipart/form-data'}}) },
  removeDocument: (id: string) => client.delete(`/knowledge/documents/${id}`),
}

