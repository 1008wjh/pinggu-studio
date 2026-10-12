<template>
  <div class="knowledge-page">
    <div class="page-heading"><div><h2>知识库管理</h2><p>创建隔离知识库并绑定专业智能体；每个智能体只检索自身绑定的库。</p></div><el-button type="primary" @click="openBaseDialog()">新建知识库</el-button></div>
    <el-card shadow="never" class="base-card">
      <el-table :data="bases" v-loading="loadingBases" highlight-current-row @current-change="selectBase">
        <el-table-column prop="name" label="知识库名称" min-width="190" />
        <el-table-column label="绑定智能体" min-width="220"><template #default="{row}"><el-tag v-for="agent in row.agents" :key="agent.key" size="small" class="agent-tag">{{ agent.name }}</el-tag><span v-if="!row.agents.length" class="muted">未绑定</span></template></el-table-column>
        <el-table-column prop="document_count" label="文档数量" width="100" />
        <el-table-column prop="created_at" label="创建时间" width="180"><template #default="{row}">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="170"><template #default="{row}"><el-button link type="primary" @click.stop="openBaseDialog(row)">编辑</el-button><el-button link type="danger" :disabled="row.name==='默认工作室知识库'" @click.stop="removeBase(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-pagination v-if="total > pageSize" v-model:current-page="page" :page-size="pageSize" :total="total" layout="prev, pager, next" @current-change="loadBases" />
    </el-card>

    <el-card v-if="selectedBase" shadow="never" class="documents-card">
      <template #header><div class="document-header"><div><b>{{ selectedBase.name }}</b><span class="muted"> · {{ selectedBase.description || '暂无描述' }}</span></div><div><input ref="uploadInput" class="file-input" type="file" accept=".txt,.md,.pdf,.docx,.csv,.tsv,.xlsx,.xlsm,.json" @change="uploadDocument" /><el-button type="primary" :loading="uploading" @click="uploadInput?.click()">上传文档入库</el-button></div></div></template>
      <el-alert v-if="selectedBase.agents.length" :title="`当前绑定：${selectedBase.agents.map(item => item.name).join('、')}；向量 partition：${selectedBase.milvus_partition}`" type="info" :closable="false" class="base-info" />
      <el-table :data="documents" v-loading="loadingDocs" stripe>
        <el-table-column prop="title" label="文档名称" min-width="220" />
        <el-table-column prop="source_name" label="文件名" min-width="180" />
        <el-table-column prop="chunk_count" label="切片" width="80" />
        <el-table-column label="向量" width="90"><template #default="{row}"><el-tag :type="row.vector_count === row.chunk_count ? 'success' : 'warning'" size="small">{{ row.vector_count }}/{{ row.chunk_count }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{row}"><el-tag :type="row.status === 'ready' ? 'success' : 'warning'" size="small">{{ row.status === 'ready' ? '已就绪' : '待补写向量' }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="入库时间" width="180"><template #default="{row}">{{ formatTime(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="220"><template #default="{row}"><el-button link type="primary" @click="previewDocument(row)">切片预览</el-button><el-button link type="primary" @click="replaceDocument(row)">重新上传</el-button><el-button link type="danger" @click="removeDocument(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-empty v-if="!loadingDocs && !documents.length" description="该知识库还没有文档" />
    </el-card>

    <el-dialog v-model="baseDialogVisible" :title="editingBase ? '编辑知识库' : '新建知识库'" width="520px">
      <el-form :model="baseForm" label-position="top"><el-form-item label="知识库名称" required><el-input v-model="baseForm.name" maxlength="128" /></el-form-item><el-form-item label="描述"><el-input v-model="baseForm.description" type="textarea" :rows="3" /></el-form-item><el-form-item label="绑定专业智能体"><el-checkbox-group v-model="baseForm.agent_keys"><el-checkbox v-for="agent in agentOptions" :key="agent.key" :label="agent.key">{{ agent.name }}</el-checkbox></el-checkbox-group></el-form-item></el-form>
      <template #footer><el-button @click="baseDialogVisible=false">取消</el-button><el-button type="primary" :loading="savingBase" @click="saveBase">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="previewVisible" :title="preview?.title || '文档切片预览'" width="760px"><el-descriptions v-if="preview" :column="3" border size="small"><el-descriptions-item label="文件">{{ preview.source_name }}</el-descriptions-item><el-descriptions-item label="切片数">{{ preview.chunk_count }}</el-descriptions-item><el-descriptions-item label="向量数">{{ preview.vector_count }}</el-descriptions-item></el-descriptions><el-collapse v-if="preview" class="chunk-list"><el-collapse-item v-for="chunk in preview.chunks" :key="chunk.id" :name="chunk.id"><template #title>第 {{ chunk.chunk_index + 1 }} 个切片</template><pre>{{ chunk.content }}</pre></el-collapse-item></el-collapse></el-dialog>

    <input ref="replaceInput" class="file-input" type="file" accept=".txt,.md,.pdf,.docx,.csv,.tsv,.xlsx,.xlsm,.json" @change="onReplaceFile" />
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeApi, type KnowledgeBase, type KnowledgeDocument, type KnowledgeDocumentDetail } from '@/api/knowledge'
const bases=ref<KnowledgeBase[]>([]); const total=ref(0); const page=ref(1); const pageSize=20; const loadingBases=ref(false); const selectedBase=ref<KnowledgeBase|null>(null); const documents=ref<KnowledgeDocument[]>([]); const loadingDocs=ref(false); const uploading=ref(false); const savingBase=ref(false); const uploadInput=ref<HTMLInputElement|null>(null); const replaceInput=ref<HTMLInputElement|null>(null); const replacing=ref<KnowledgeDocument|null>(null)
const baseDialogVisible=ref(false); const editingBase=ref<KnowledgeBase|null>(null); const baseForm=ref({name:'',description:'',agent_keys:['domain_qa']}); const previewVisible=ref(false); const preview=ref<KnowledgeDocumentDetail|null>(null)
const agentOptions=[{key:'domain_qa',name:'专业问答'},{key:'land_assessment',name:'文书要点摘要'}]
async function loadBases(){loadingBases.value=true;try{const r=await knowledgeApi.listBases(page.value,pageSize);bases.value=r.data.items;total.value=r.data.total;if(!selectedBase.value && bases.value.length)selectBase(bases.value[0]);else if(selectedBase.value){const fresh=bases.value.find(item=>item.id===selectedBase.value?.id);if(fresh)selectBase(fresh)}}finally{loadingBases.value=false}}
async function selectBase(base:KnowledgeBase|null){if(!base)return;selectedBase.value=base;loadingDocs.value=true;try{documents.value=(await knowledgeApi.listDocuments(base.id)).data.items}finally{loadingDocs.value=false}}
function openBaseDialog(base?:KnowledgeBase){editingBase.value=base||null;baseForm.value={name:base?.name||'',description:base?.description||'',agent_keys:base?.agents.map(item=>item.key)||['domain_qa']};baseDialogVisible.value=true}
async function saveBase(){if(!baseForm.value.name.trim()){ElMessage.warning('请输入知识库名称');return};savingBase.value=true;try{if(editingBase.value)await knowledgeApi.updateBase(editingBase.value.id,baseForm.value);else await knowledgeApi.createBase(baseForm.value);ElMessage.success('知识库已保存');baseDialogVisible.value=false;await loadBases()}finally{savingBase.value=false}}
async function removeBase(base:KnowledgeBase){await ElMessageBox.confirm(`删除知识库“${base.name}”及其全部文档？`,'删除确认',{type:'warning'});await knowledgeApi.removeBase(base.id);if(selectedBase.value?.id===base.id)selectedBase.value=null;ElMessage.success('知识库已删除');await loadBases()}
async function uploadDocument(e:Event){const file=(e.target as HTMLInputElement).files?.[0];(e.target as HTMLInputElement).value='';if(!file||!selectedBase.value)return;uploading.value=true;try{await knowledgeApi.upload(selectedBase.value.id,file);ElMessage.success('文档入库完成');await loadBases();await selectBase(bases.value.find(item=>item.id===selectedBase.value?.id)||selectedBase.value)}finally{uploading.value=false}}
async function previewDocument(doc:KnowledgeDocument){preview.value=(await knowledgeApi.getDocument(doc.id)).data;previewVisible.value=true}
function replaceDocument(doc:KnowledgeDocument){replacing.value=doc;replaceInput.value?.click()}
async function onReplaceFile(e:Event){const file=(e.target as HTMLInputElement).files?.[0];(e.target as HTMLInputElement).value='';if(!file||!replacing.value)return;uploading.value=true;try{await knowledgeApi.updateDocument(replacing.value.id,file,replacing.value.title);ElMessage.success('文档已更新并重新切片');if(selectedBase.value)await selectBase(selectedBase.value)}finally{uploading.value=false}}
async function removeDocument(doc:KnowledgeDocument){await ElMessageBox.confirm(`删除文档“${doc.title}”？`,'删除确认',{type:'warning'});await knowledgeApi.removeDocument(doc.id);ElMessage.success('文档已删除');if(selectedBase.value)await selectBase(selectedBase.value)}
function formatTime(value?:string){return value?new Date(value).toLocaleString():'—'}
onMounted(loadBases)
</script>
<style scoped>.knowledge-page{max-width:1240px}.page-heading{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}.page-heading h2{margin:0 0 6px}.page-heading p,.muted{margin:0;color:#8c8c8c}.base-card,.documents-card{margin-bottom:16px}.agent-tag{margin-right:6px}.document-header{display:flex;align-items:center;justify-content:space-between}.base-info{margin-bottom:14px}.file-input{display:none}.el-pagination{justify-content:flex-end;margin-top:16px}.chunk-list{margin-top:18px}.chunk-list pre{white-space:pre-wrap;background:#f7f8fa;border-radius:6px;padding:12px;line-height:1.6;max-height:360px;overflow:auto}</style>


