<template>
  <div class="workspace-page">
    <div class="page-heading">
      <div>
        <h2>文档与表格工作台</h2>
        <p>面向合同、招投标和企业制度资料的文档抽取、表格检查与合并工具。</p>
      </div>
      <el-tag type="success" effect="light">工作台 Agent 已接入</el-tag>
    </div>

    <el-tabs v-model="activeTab" type="card">
      <el-tab-pane label="文档抽取" name="extract">
        <el-card shadow="never" class="tool-card">
          <div class="tool-intro">
            <h3>抽取文档信息</h3>
            <p>支持 PDF、DOCX、TXT、Markdown、JSON、CSV、TSV 和 XLSX。</p>
          </div>
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".pdf,.docx,.txt,.md,.json,.csv,.tsv,.xlsx,.xlsm"
            @change="handleExtractFile"
          >
            <el-button type="primary" :loading="extracting">选择文件并抽取</el-button>
          </el-upload>
          <div v-if="extractFileName" class="selected-file">已选择：{{ extractFileName }}</div>
<el-input-number v-if="!extractAll" v-model="maxRows" :min="1" :max="1000" controls-position="right" />
          <el-checkbox v-model="extractAll">最大（抽取完整文档）</el-checkbox>
          <span class="field-hint">表格最多返回行数</span>
        </el-card>
        <el-card v-if="extractResult" shadow="never" class="result-card">
          <template #header><span>抽取结果</span></template>
          <el-button type="success" plain :loading="summarizing" :disabled="!extractFile" @click="runSummary">智能总结</el-button>
          <el-tabs v-model="extractResultTab">
            <el-tab-pane label="结构化预览" name="pretty">
              <pre class="json-result">{{ pretty(extractResult) }}</pre>
            </el-tab-pane>
            <el-tab-pane v-if="summaryResult" label="智能总结" name="summary">
              <div class="summary-text">{{ summaryResult.summary }}</div>
            </el-tab-pane>
            <el-tab-pane v-if="extractResult.text" label="纯文本" name="text">
              <div class="plain-text">{{ extractResult.text }}</div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="表格检查" name="inspect">
        <el-card shadow="never" class="tool-card">
          <div class="tool-intro">
            <h3>检查表格结构</h3>
            <p>先查看工作表、表头和预览行，再决定是否合并。</p>
          </div>
          <el-upload :auto-upload="false" :show-file-list="false" accept=".csv,.tsv,.xlsx,.xlsm" @change="handleInspectFile">
            <el-button type="primary" :loading="inspecting">选择表格并检查</el-button>
          </el-upload>
          <div v-if="inspectResult" class="sheet-list">
            <el-card v-for="sheet in inspectResult.sheets" :key="sheet.name" shadow="never" class="sheet-card">
              <template #header><span>{{ sheet.name }}</span><el-tag size="small">{{ sheet.headers.length }} 列</el-tag></template>
              <el-table :data="sheet.rows" border stripe size="small" max-height="360">
                <el-table-column v-for="header in sheet.headers" :key="header" :prop="header" :label="header" min-width="140" show-overflow-tooltip />
              </el-table>
            </el-card>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="表格合并" name="merge">
        <el-card shadow="never" class="tool-card">
          <div class="tool-intro">
            <h3>合并多个表格</h3>
            <p>按表头自动取并集，缺失字段留空，并保留来源文件和工作表信息。</p>
          </div>
          <input ref="mergeInput" class="file-input" type="file" multiple accept=".csv,.tsv,.xlsx,.xlsm" @change="onMergeSelected" />
          <el-button :disabled="merging" @click="openMergePicker">选择表格文件</el-button>
          <el-button :disabled="merging || mergeFiles.length === 0" @click="clearMergeFiles">清空已选</el-button>
          <el-button type="primary" :loading="merging" :disabled="mergeFiles.length === 0" @click="runMerge">合并并下载 XLSX</el-button>
          <div v-if="mergeFiles.length" class="file-list">
            <el-tag v-for="file in mergeFiles" :key="file.name + file.size" closable @close="removeMergeFile(file)">{{ file.name }}</el-tag>
          </div>
          <el-alert v-if="mergeMessage" :title="mergeMessage" :type="mergeError ? 'error' : 'success'" show-icon :closable="false" class="merge-alert" />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, type UploadFile } from 'element-plus'
import { workspaceApi, type WorkspaceTableResult } from '@/api/workspace'

const activeTab = ref('extract')
const extractResultTab = ref('pretty')
const maxRows = ref(200)
const extractAll = ref(false)
const extractFile = ref<File | null>(null)
const summarizing = ref(false)
const summaryResult = ref<{ summary: string } | null>(null)
const extracting = ref(false)
const inspecting = ref(false)
const merging = ref(false)
const extractFileName = ref('')
const extractResult = ref<Record<string, any> | null>(null)
const inspectResult = ref<WorkspaceTableResult | null>(null)
const mergeFiles = ref<File[]>([])
const mergeInput = ref<HTMLInputElement | null>(null)
const mergeMessage = ref('')
const mergeError = ref(false)

async function handleExtractFile(upload: UploadFile) {
  if (!upload.raw) return
  extractFileName.value = upload.name
  extractFile.value = upload.raw
  summaryResult.value = null
  extracting.value = true
  try {
    const response = await workspaceApi.extract(upload.raw, extractAll.value ? undefined : maxRows.value)
    extractResult.value = response.data
    extractResultTab.value = response.data.text ? 'text' : 'pretty'
    ElMessage.success('文档抽取完成')
  } catch {
    extractResult.value = null
  } finally {
    extracting.value = false
  }
}

async function runSummary() {
  if (!extractFile.value) return
  summarizing.value = true
  try {
    const response = await workspaceApi.summarize(extractFile.value, extractAll.value ? undefined : maxRows.value)
    summaryResult.value = response.data
    extractResultTab.value = 'summary'
    ElMessage.success('智能总结完成')
  } finally {
    summarizing.value = false
  }
}
async function handleInspectFile(upload: UploadFile) {
  if (!upload.raw) return
  inspecting.value = true
  try {
    const response = await workspaceApi.inspect(upload.raw)
    inspectResult.value = response.data
    ElMessage.success('表格读取完成')
  } catch {
    inspectResult.value = null
  } finally {
    inspecting.value = false
  }
}

function openMergePicker() {
  mergeInput.value?.click()
}
function onMergeSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const selected = Array.from(input.files ?? [])
  const existing = new Set(mergeFiles.value.map(file => `${file.name}:${file.size}:${file.lastModified}`))
  for (const file of selected) {
    const key = `${file.name}:${file.size}:${file.lastModified}`
    if (!existing.has(key)) {
      mergeFiles.value.push(file)
      existing.add(key)
    }
  }
  input.value = ''
  mergeMessage.value = ''
}

function clearMergeFiles() {
  mergeFiles.value = []
  mergeMessage.value = ''
}

function removeMergeFile(file: File) {
  mergeFiles.value = mergeFiles.value.filter(item => item !== file)
}

async function runMerge() {
  merging.value = true
  mergeMessage.value = ''
  mergeError.value = false
  try {
    const response = await workspaceApi.merge(mergeFiles.value)
    const url = URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = 'merged_result.xlsx'
    link.click()
    URL.revokeObjectURL(url)
    mergeMessage.value = '合并完成，文件已开始下载。'
  } catch {
    mergeError.value = true
    mergeMessage.value = '合并失败，请确认文件格式和后端服务状态。'
  } finally {
    merging.value = false
  }
}

function pretty(value: unknown) {
  return JSON.stringify(value, null, 2)
}
</script>

<style scoped>
.workspace-page { max-width: 1180px; }
.page-heading { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 20px; }
.page-heading h2 { margin: 0 0 6px; font-size: 22px; }
.page-heading p, .tool-intro p { margin: 0; color: #8c8c8c; }
.tool-card, .result-card { margin-bottom: 16px; }
.tool-intro { margin-bottom: 18px; }
.tool-intro h3 { margin: 0 0 6px; font-size: 16px; }
.selected-file { display: inline-block; margin: 12px 18px 0 12px; color: #595959; font-size: 13px; }
.field-hint { margin-left: 8px; color: #8c8c8c; font-size: 13px; }
.json-result { max-height: 620px; overflow: auto; padding: 16px; margin: 0; background: #f7f8fa; border-radius: 6px; color: #334155; font-size: 12px; line-height: 1.6; white-space: pre-wrap; }
.summary-text { max-height: 620px; overflow: auto; padding: 16px; background: #f7f8fa; white-space: pre-wrap; line-height: 1.8; color: #334155; } .plain-text { max-height: 620px; overflow: auto; padding: 16px; background: #f7f8fa; white-space: pre-wrap; line-height: 1.7; color: #334155; }
.sheet-list { margin-top: 18px; display: grid; gap: 14px; }
.sheet-card :deep(.el-card__header) { display: flex; justify-content: space-between; align-items: center; }
.file-input { display: none; }
.file-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.merge-alert { margin-top: 18px; }
</style>







