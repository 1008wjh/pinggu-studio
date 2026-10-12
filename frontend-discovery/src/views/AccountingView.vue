<template>
  <div class="accounting-page">
    <div class="page-heading">
      <div><h2>审查工作流</h2><p>四步串联：单据分类 → 会计凭证 → 三大报表 → 同比/环比/季度分析。每一步都必须人工确认并留下审计记录。</p></div>
      <el-tag type="warning">四步强制人工复核</el-tag>
    </div>

    <el-card v-if="!workflow" shadow="never" class="start-card">
      <template #header><span>创建核算工作流</span></template>
      <el-alert title="建议先上传企业科目分类规则和银行流水；历史报表用于第四步期间对比。" type="info" :closable="false" show-icon class="notice" />
      <el-form label-position="top">
        <el-form-item label="原始发票（图片 / PDF / Excel，可多选）" required>
          <input ref="invoiceInput" class="file-input" type="file" multiple accept=".png,.jpg,.jpeg,.tif,.tiff,.pdf,.docx,.txt,.csv,.xlsx,.xls" @change="pickInvoices" />
          <el-button @click="invoiceInput?.click()">选择发票</el-button>
          <div v-if="invoiceFiles.length" class="file-list"><el-tag v-for="file in invoiceFiles" :key="file.name + file.size">{{ file.name }}</el-tag></div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8"><el-form-item label="企业科目分类规则"><input ref="rulesInput" class="file-input" type="file" accept=".txt,.md,.docx,.pdf,.csv,.xlsx,.xls" @change="pickRules" /><el-button @click="rulesInput?.click()">选择规则文件</el-button><span v-if="rulesFile" class="inline-file">{{ rulesFile.name }}</span></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="银行流水明细"><input ref="bankInput" class="file-input" type="file" accept=".txt,.md,.csv,.xlsx,.xls,.pdf" @change="pickBank" /><el-button @click="bankInput?.click()">选择银行流水</el-button><span v-if="bankFile" class="inline-file">{{ bankFile.name }}</span></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="历史报表（可多选）"><input ref="historyInput" class="file-input" type="file" multiple accept=".txt,.md,.csv,.xlsx,.xls,.pdf" @change="pickHistory" /><el-button @click="historyInput?.click()">选择历史报表</el-button><span v-if="historyFiles.length" class="inline-file">已选 {{ historyFiles.length }} 份</span></el-form-item></el-col>
        </el-row>
        <el-form-item><el-checkbox v-model="useLlm">启用 DeepSeek 语义复核（不可用时自动使用规则引擎）</el-checkbox></el-form-item>
        <el-button type="primary" :loading="starting" :disabled="!invoiceFiles.length" @click="startWorkflow">开始四步核算</el-button>
      </el-form>
      <div v-if="pendingWorkflows.length" class="pending-list">
        <div class="panel-title">未完成工作流</div>
        <el-button v-for="item in pendingWorkflows" :key="item.id" class="pending-item" @click="resumeSaved(item.id)">
          {{ item.id }} · {{ stepTitle(item.current_step) }} · {{ statusLabel(item.status) }}
        </el-button>
      </div>
    </el-card>

    <template v-else>
      <el-card shadow="never" class="progress-card">
        <div class="workflow-top"><div><b>工作流 {{ workflow.workflow_id }}</b><span class="muted">Checkpoint #{{ workflow.checkpoint_version }}</span></div><div class="workflow-actions"><el-tag :type="workflow.status === 'completed' ? 'success' : 'warning'">{{ statusLabel(workflow.status) }}</el-tag><el-button v-if="workflow.status !== 'completed'" size="small" @click="exitWorkflow">退出当前流程</el-button></div></div>
        <el-steps :active="activeStep" finish-status="success" align-center><el-step v-for="item in steps" :key="item.key" :title="item.title" :description="stepDescription(item.key)" /></el-steps>
      </el-card>

      <el-card v-if="workflow.status !== 'completed'" shadow="never" class="review-card">
        <template #header><div class="review-header"><span>待审核：{{ currentStepTitle }}</span><el-tag type="warning">必须人工操作后继续</el-tag></div></template>
        <el-descriptions :column="4" border size="small" class="score-grid"><el-descriptions-item label="置信度"><el-progress :percentage="Math.round((workflow.confidence || 0) * 100)" :status="workflow.confidence >= .8 ? 'success' : 'exception'" /></el-descriptions-item><el-descriptions-item label="风险分数"><el-progress :percentage="Math.round((workflow.risk || 0) * 100)" :status="workflow.risk <= .2 ? 'success' : 'exception'" /></el-descriptions-item><el-descriptions-item label="当前节点">{{ currentStepTitle }}</el-descriptions-item><el-descriptions-item label="人工操作">确认 / 上传修改表格 / 打回</el-descriptions-item></el-descriptions>
        <el-alert v-if="reviewAnomalies.length" title="检测到需要关注的异常" type="warning" :closable="false" class="notice"><template #default><ul><li v-for="(item, index) in reviewAnomalies" :key="index">{{ typeof item === 'string' ? item : pretty(item) }}</li></ul></template></el-alert>
        <el-row :gutter="16" class="data-panels"><el-col :span="8"><div class="panel-title">原始数据</div><pre>{{ pretty(workflow.review?.original_data) }}</pre></el-col><el-col :span="8"><div class="panel-title">AI 原始输出（只读）</div><pre>{{ pretty(workflow.review?.ai_output) }}</pre></el-col><el-col :span="8"><div class="panel-title">表格预览</div><div v-if="tablePreviews.length" class="table-previews"><div v-for="sheet in tablePreviews" :key="sheet.workbook + sheet.sheet" class="table-preview"><b>{{ sheet.workbook }} / {{ sheet.sheet }}</b><el-table :data="sheet.rows" size="small" border max-height="260"><el-table-column v-for="header in sheet.headers" :key="header" :prop="header" :label="header" min-width="120" show-overflow-tooltip /></el-table></div></div><pre v-else>{{ pretty(workflow.review?.display_data || workflow.review?.ai_output) }}</pre></el-col></el-row>
        <div class="rules-box"><b>参考规则：</b>{{ workflow.review?.rules || '当前节点使用企业规则、借贷平衡和报表勾稽校验。' }}</div>
        <div v-if="tableFiles.length" class="report-files"><b>本步骤结果表格：</b><el-button v-for="file in tableFiles" :key="`table-${file.key}`" link type="primary" @click="downloadTable(file)">下载 {{ file.name }}</el-button></div>
        <div v-if="reportFiles.length" class="report-files"><b>三大报表：</b><el-button v-for="file in reportFiles" :key="`report-${file.key}`" link type="primary" @click="downloadReport(file)">下载 {{ file.name }}</el-button></div>
        <div class="model-note" v-if="modelNote"><b>模型意见：</b><div class="markdown-body" v-html="renderMarkdown(modelNote.summary)"></div><ul v-if="modelNote.anomalies?.length"><li v-for="item in modelNote.anomalies" :key="item">{{ item }}</li></ul></div>
        <el-divider />
        <div class="action-area">
          <el-button type="success" :loading="resuming" @click="resume('approve')">确认通过，进入下一步</el-button>
          <input ref="tableInput" class="file-input" type="file" accept=".xlsx,.xls,.xlsm,.csv" @change="pickTable" />
          <el-button v-if="workflow.current_step !== 'step4_comparison'" type="primary" plain @click="tableInput?.click()">上传线下修改后的表格</el-button>
          <el-button v-if="workflow.current_step === 'step4_comparison'" type="primary" plain @click="editorVisible = !editorVisible">修改总结内容</el-button>
          <el-button type="warning" plain @click="returnVisible = !returnVisible">填写备注打回重跑</el-button>
        </div>
        <div v-if="tableFile" class="editor-box"><div class="panel-title">待上传的线下修改表格</div><span class="inline-file">{{ tableFile.name }}</span><el-button type="primary" :loading="uploadingTable" @click="uploadTable">提交表格并继续</el-button></div>
        <div v-if="editorVisible && workflow.current_step === 'step4_comparison'" class="editor-box"><div class="panel-title">修改总结内容（JSON）</div><el-input v-model="editedJson" type="textarea" :rows="10"/><div class="editor-actions"><el-button @click="editorVisible=false">取消</el-button><el-button type="primary" :loading="resuming" @click="submitEdit">提交修改并继续</el-button></div></div>
        <div v-if="returnVisible" class="editor-box"><div class="panel-title">打回原因（必填）</div><el-input v-model="returnComment" type="textarea" :rows="3" placeholder="说明需要重新识别或重算的原因"/><div class="editor-actions"><el-button @click="returnVisible=false">取消</el-button><el-button type="warning" :loading="resuming" @click="submitReturn">打回当前节点重跑</el-button></div></div>
      </el-card>

      <el-card v-else shadow="never" class="complete-card"><el-result icon="success" title="审查工作流已完成" sub-title="四步均已人工确认，所有结果和操作已写入审计记录。"><template #extra><el-button type="primary" @click="reset">新建一条核算工作流</el-button></template></el-result><el-collapse><el-collapse-item v-for="item in steps" :key="item.key" :title="item.title" :name="item.key"><pre>{{ pretty(workflow.step_outputs?.[item.key]) }}</pre></el-collapse-item></el-collapse></el-card>

      <el-card shadow="never" class="audit-card"><template #header><span>审计时间线</span></template><el-timeline><el-timeline-item v-for="(item, index) in workflow.audit_logs || []" :key="index" :timestamp="formatTime(item.created_at)" type="primary">{{ item.event_type }} · {{ item.step_name || '工作流' }}<div class="audit-detail">{{ pretty(item.payload) }}</div></el-timeline-item></el-timeline><el-empty v-if="!workflow.audit_logs?.length" description="暂无审计记录" /></el-card>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountingApi, type AccountingAction, type AccountingWorkflow } from '@/api/accounting'
import MarkdownIt from 'markdown-it'
const steps=[{key:'step1_classification',title:'单据分类打标'},{key:'step2_vouchers',title:'会计分录凭证'},{key:'step3_statements',title:'三大财务报表'},{key:'step4_comparison',title:'同比/环比分析'}]
const workflow=ref<AccountingWorkflow|null>(null); const pendingWorkflows=ref<Array<{id:string;status:string;current_step:string}>>([]); const starting=ref(false); const resuming=ref(false); const editorVisible=ref(false); const returnVisible=ref(false); const editedJson=ref(''); const returnComment=ref(''); const useLlm=ref(true); const invoiceFiles=ref<File[]>([]); const rulesFile=ref<File|null>(null); const bankFile=ref<File|null>(null); const historyFiles=ref<File[]>([]); const tableFile=ref<File|null>(null); const uploadingTable=ref(false)
const invoiceInput=ref<HTMLInputElement|null>(null); const rulesInput=ref<HTMLInputElement|null>(null); const bankInput=ref<HTMLInputElement|null>(null); const historyInput=ref<HTMLInputElement|null>(null); const tableInput=ref<HTMLInputElement|null>(null)
const activeStep=computed(()=>Math.max(0,steps.findIndex(item=>item.key===workflow.value?.current_step))); const currentStepTitle=computed(()=>steps.find(item=>item.key===workflow.value?.current_step)?.title || '工作流'); const reviewAnomalies=computed(()=>{const data=workflow.value?.review?.ai_output as any; return data?.anomalies || []})
const isClassification=computed(()=>workflow.value?.current_step==='step1_classification'); const displayInvoices=computed(()=>((workflow.value?.review?.display_data as any)?.invoices || []) as Array<Record<string, unknown>>); const modelNote=computed(()=>{const raw=(workflow.value?.review?.ai_output as any)?.model_note; return typeof raw==='string' ? {summary:raw,anomalies:[]} : (raw || null)}) ; const markdown=new MarkdownIt({html:false,breaks:true,linkify:true})
const tableFiles=computed(()=>(((workflow.value?.review?.display_data as any)?.table_files || (workflow.value?.step_outputs?.[workflow.value?.current_step || ''] as any)?.table_files || []) as Array<{key:string;name:string;download_url:string}>))
const reportFiles=computed(()=>(((workflow.value?.review?.display_data as any)?.report_files || (workflow.value?.step_outputs?.[workflow.value?.current_step || ''] as any)?.report_files || []) as Array<{key:string;name:string}>))
const tablePreviews=computed(()=>(((workflow.value?.review?.display_data as any)?.table_preview || (workflow.value?.step_outputs?.[workflow.value?.current_step || ''] as any)?.table_preview || []) as Array<any>))
function statusLabel(status:string){return status==='completed'?'已完成':status==='pending_review'?'待人工审核':status==='running'?'处理中':status}
function stepTitle(key:string){return steps.find(item=>item.key===key)?.title || key}
function stepDescription(key:string){if(!workflow.value)return ''; if(workflow.value.status==='completed'||workflow.value.step_outputs?.[key])return '已生成'; if(workflow.value.current_step===key)return '待审核'; return '等待前置步骤'}
function pretty(value:unknown){return JSON.stringify(value??{},null,2)}
function renderMarkdown(value:string){return markdown.render(value || '')}
function formatTime(value:string|undefined){return value?new Date(value).toLocaleString():'刚刚'}
function pickInvoices(e:Event){invoiceFiles.value=Array.from((e.target as HTMLInputElement).files??[]);(e.target as HTMLInputElement).value=''}
function pickRules(e:Event){rulesFile.value=(e.target as HTMLInputElement).files?.[0]??null;(e.target as HTMLInputElement).value=''}
function pickBank(e:Event){bankFile.value=(e.target as HTMLInputElement).files?.[0]??null;(e.target as HTMLInputElement).value=''}
function pickHistory(e:Event){historyFiles.value=Array.from((e.target as HTMLInputElement).files??[]);(e.target as HTMLInputElement).value=''}
function pickTable(e:Event){tableFile.value=(e.target as HTMLInputElement).files?.[0]??null;(e.target as HTMLInputElement).value=''}
async function startWorkflow(){const form=new FormData();invoiceFiles.value.forEach(file=>form.append('invoice_files',file));if(rulesFile.value)form.append('rules_file',rulesFile.value);if(bankFile.value)form.append('bank_file',bankFile.value);historyFiles.value.forEach(file=>form.append('history_files',file));form.append('use_llm',String(useLlm.value));starting.value=true;try{workflow.value=(await accountingApi.start(form)).data;localStorage.setItem('accounting_active_workflow',workflow.value.workflow_id);syncEditor();ElMessage.success('第一步已生成，等待人工审核')}finally{starting.value=false}}
function syncEditor(){editedJson.value=workflow.value?.current_step === 'step4_comparison' ? pretty(workflow.value?.review?.display_data || workflow.value?.review?.ai_output) : ''}
async function loadSavedWorkflows(restoreActive=true){try{const result=await accountingApi.list();pendingWorkflows.value=result.data.items.filter(item=>item.status!=='completed');if(!restoreActive)return;const saved=localStorage.getItem('accounting_active_workflow');const candidate=pendingWorkflows.value.find(item=>item.id===saved) || pendingWorkflows.value[0];if(candidate) await resumeSaved(candidate.id)}catch{/* 登录后接口不可用时仍保留新建页面 */}}
async function resumeSaved(id:string){workflow.value=(await accountingApi.get(id)).data;localStorage.setItem('accounting_active_workflow',id);syncEditor()}
async function resume(action:AccountingAction, edited:Record<string,unknown>={}, comment=''){if(!workflow.value)return;resuming.value=true;try{workflow.value=(await accountingApi.resume(workflow.value.workflow_id,action,edited,comment)).data;editorVisible.value=false;returnVisible.value=false;syncEditor();ElMessage.success(workflow.value.status==='completed'?'四步核算已完成':'已进入下一步待审核')}finally{resuming.value=false}}
async function uploadTable(){if(!workflow.value || !tableFile.value)return; uploadingTable.value=true; try{workflow.value=(await accountingApi.uploadTable(workflow.value.workflow_id,tableFile.value)).data; tableFile.value=null; ElMessage.success('已接收修改后的表格并进入下一步待审核'); syncEditor()}catch{ElMessage.error('表格上传失败，请检查工作表和列名')}finally{uploadingTable.value=false}}
async function submitEdit(){try{const data=JSON.parse(editedJson.value);await resume('edit',data,'人工修改最后一步总结')}catch{ElMessage.error('修改内容必须是合法 JSON')}}
async function submitReturn(){if(!returnComment.value.trim()){ElMessage.warning('请填写打回原因');return}await resume('return',{},returnComment.value);returnComment.value=''}
async function downloadTable(file:{key:string;name:string}){if(!workflow.value)return;try{const response=await accountingApi.downloadTable(workflow.value.workflow_id,file.key);const url=URL.createObjectURL(response.data);const anchor=document.createElement('a');anchor.href=url;anchor.download=file.name;anchor.click();URL.revokeObjectURL(url)}catch{ElMessage.error('表格下载失败，请重试')}}
async function downloadReport(file:{key:string;name:string}){if(!workflow.value)return;try{const response=await accountingApi.downloadReport(workflow.value.workflow_id,file.key);const url=URL.createObjectURL(response.data);const anchor=document.createElement('a');anchor.href=url;anchor.download=file.name;anchor.click();URL.revokeObjectURL(url)}catch{ElMessage.error('报表下载失败，请重试')}}
async function exitWorkflow(){if(!workflow.value)return;try{await ElMessageBox.confirm('退出后将丢弃当前未完成工作流、上传材料和审核进度，确定继续吗？','退出并丢弃',{type:'warning',confirmButtonText:'退出并丢弃',cancelButtonText:'取消'});await accountingApi.discard(workflow.value.workflow_id);localStorage.removeItem('accounting_active_workflow');workflow.value=null;editorVisible.value=false;returnVisible.value=false;await loadSavedWorkflows(false);ElMessage.success('已退出当前工作流，页面已回到初始状态')}catch(error){if(error !== 'cancel') ElMessage.error('退出工作流失败')}}
function reset(){workflow.value=null;pendingWorkflows.value=[];localStorage.removeItem('accounting_active_workflow');invoiceFiles.value=[];rulesFile.value=null;bankFile.value=null;historyFiles.value=[]}
onMounted(loadSavedWorkflows)
</script>
<style scoped>.accounting-page{max-width:1240px}.page-heading{display:flex;justify-content:space-between;gap:24px;margin-bottom:20px}.page-heading h2{margin:0 0 6px}.page-heading p,.muted{color:#8c8c8c;margin:0}.start-card,.progress-card,.review-card,.complete-card,.audit-card{margin-bottom:16px}.notice{margin-bottom:18px}.file-input{display:none}.file-list{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.inline-file{margin-left:10px;color:#606266;font-size:13px}.pending-list{margin-top:24px;padding-top:16px;border-top:1px solid #ebeef5}.pending-item{display:block;width:100%;text-align:left;margin:8px 0}.workflow-top,.review-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px}.workflow-actions{display:flex;align-items:center;gap:10px}.workflow-top .muted{margin-left:14px;font-size:12px}.score-grid{margin:14px 0}.data-panels{margin-top:18px}.panel-title{font-weight:600;color:#606266;margin-bottom:6px}.data-panels pre,.complete-card pre{max-height:380px;overflow:auto;background:#f7f8fa;border-radius:6px;padding:12px;font-size:12px;line-height:1.55;white-space:pre-wrap}.rules-box,.model-note,.report-files{padding:12px;background:#f8fafc;border-left:3px solid #409eff;margin-top:12px;white-space:pre-wrap}.report-files{display:flex;gap:16px;align-items:center;flex-wrap:wrap}.model-note{border-left-color:#67c23a}.markdown-body :deep(h1),.markdown-body :deep(h2),.markdown-body :deep(h3){margin:4px 0 8px;font-size:14px}.action-area{display:flex;gap:10px;flex-wrap:wrap}.editor-box{margin-top:18px;padding:16px;background:#fafafa;border:1px solid #ebeef5;border-radius:6px}.editor-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:12px}.audit-detail{margin-top:4px;color:#909399;font-size:12px;white-space:pre-wrap;max-height:140px;overflow:auto}</style>


