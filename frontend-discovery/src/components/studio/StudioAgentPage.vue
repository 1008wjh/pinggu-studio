<template>
  <div class="workspace" :class="{ compact: !sessionsOpen }">
    <aside class="sessions">
      <div class="sessions-head"><strong v-if="sessionsOpen">会话 <small>{{ conversations.length }}</small></strong><el-button text :icon="sessionsOpen ? Fold : Expand" :title="sessionsOpen ? '收起会话' : '展开会话'" @click="sessionsOpen = !sessionsOpen" /></div>
      <el-button class="new-session" :icon="Plus" :title="!sessionsOpen ? '新建会话' : ''" @click="newConversation">{{ sessionsOpen ? '新建会话' : '' }}</el-button>
      <template v-if="sessionsOpen"><div class="caption">当前浏览器会话</div><button v-for="item in conversations" :key="item.id" class="session" :class="{ active: item.id === currentId }" @click="currentId = item.id"><b>{{ item.title }}</b><small>{{ item.messages.length }} 条消息</small></button></template>
    </aside>
    <section class="chat">
      <header class="chat-head"><div><small>工作室 / {{ kind === 'qa' ? '法律知识问答' : '文书要点摘要' }}</small><h1>{{ title }}</h1></div><el-tag effect="plain" type="info">{{ kind === 'qa' ? '知识库问答' : '人工复核' }}</el-tag></header>
      <div ref="messagePane" class="messages">
        <div v-if="!current.messages.length" class="empty"><el-icon><ChatDotRound /></el-icon><h2>{{ kind === 'qa' ? '开始一个新问题' : '开始一项文档审查' }}</h2><p>{{ description }}</p><div v-if="kind === 'qa'" class="prompts"><button v-for="prompt in prompts" :key="prompt" @click="question = prompt">{{ prompt }} ↗</button></div></div>
        <div v-for="message in current.messages" :key="message.id" class="message"><div class="avatar" :class="message.role">{{ message.role === 'user' ? userInitial : 'PG' }}</div><div class="message-body"><b>{{ message.role === 'user' ? username : title }} <time>{{ message.time }}</time></b><div class="message-text">{{ message.text }}</div><div v-if="message.sources?.length" class="sources">来源：{{ message.sources.join('、') }}</div><div v-if="message.files?.length" class="files"><el-tag v-for="file in message.files" :key="file" size="small" effect="plain">{{ file }}</el-tag></div></div></div>
        <div v-if="loading" class="message"><div class="avatar">PG</div><div class="message-body"><b>{{ title }}</b><div class="processing">正在处理…</div></div></div>
      </div>
      <div v-if="kind === 'land' && current.projectId" class="review"><span>初步报告待人工复核</span><div><el-button size="small" type="success" :loading="reviewing" @click="review('approved')">通过</el-button><el-button size="small" type="warning" plain :loading="reviewing" @click="review('revision_required')">要求修改</el-button><el-button size="small" type="danger" plain :loading="reviewing" @click="review('rejected')">退回</el-button></div></div>
      <div class="composer-area"><form v-if="kind === 'qa'" class="composer" @submit.prevent="ask"><textarea v-model="question" :disabled="loading" rows="2" placeholder="输入问题，开始对话…" @keydown.enter.exact.prevent="ask" /><div class="composer-actions"><span>Enter 发送 · Shift + Enter 换行</span><el-button type="primary" :icon="Promotion" circle :disabled="!question.trim() || loading" :loading="loading" native-type="submit" title="发送" /></div></form>
        <div v-else class="composer"><input ref="fileInput" type="file" class="file-input" multiple accept=".pdf,.docx,.txt,.md,.json,.csv,.tsv,.xlsx,.xlsm" @change="selectFiles" /><div class="file-toolbar"><el-button :icon="Paperclip" @click="fileInput?.click()">选择材料</el-button><span>PDF、DOCX、TXT、XLSX 等</span></div><div v-if="files.length" class="files"><el-tag v-for="file in files" :key="file.name + file.size" closable effect="plain" @close="files = files.filter(item => item !== file)">{{ file.name }}</el-tag></div><div class="composer-actions"><span>{{ files.length ? `已选择 ${files.length} 个文件` : '上传材料后生成初步报告' }}</span><el-button type="primary" :icon="Promotion" circle :disabled="!files.length || loading" :loading="loading" title="生成报告" @click="submitFiles" /></div></div>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Expand, Fold, Paperclip, Plus, Promotion } from '@element-plus/icons-vue'
import { studioApi } from '@/api/studio'
import { useAuthStore } from '@/stores/auth'
type Message = { id: number; role: 'user' | 'assistant'; text: string; time: string; sources?: string[]; files?: string[] }
type Conversation = { id: number; title: string; messages: Message[]; projectId?: string }
defineProps<{ kind: 'qa' | 'land'; title: string; description: string }>()
const auth = useAuthStore()
const username = auth.user?.username || '用户'
const userInitial = username.slice(0, 1).toUpperCase()
const prompts = ['合同中的付款条件有哪些风险？', '招标文件的资格条件是否完整？', '如何检查合同违约责任是否对等？']
const conversations = ref<Conversation[]>([{ id: 1, title: '新会话', messages: [] }])
const currentId = ref(1)
const current = computed(() => conversations.value.find(item => item.id === currentId.value) || conversations.value[0])
const sessionsOpen = ref(true)
const question = ref('')
const files = ref<File[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const messagePane = ref<HTMLElement | null>(null)
const loading = ref(false)
const reviewing = ref(false)
let nextId = 2
let nextMessageId = 1
const now = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
function scrollBottom() { nextTick(() => { if (messagePane.value) messagePane.value.scrollTop = messagePane.value.scrollHeight }) }
function addMessage(role: Message['role'], text: string, extras: Partial<Message> = {}) { current.value.messages.push({ id: nextMessageId++, role, text, time: now(), ...extras }); scrollBottom() }
function newConversation() { const item: Conversation = { id: nextId++, title: '新会话', messages: [] }; conversations.value.unshift(item); currentId.value = item.id; question.value = ''; files.value = [] }
async function ask() { const text = question.value.trim(); if (!text || loading.value) return; const target = current.value; if (target.title === '新会话') target.title = text.slice(0, 20); addMessage('user', text); question.value = ''; loading.value = true; try { const { data } = await studioApi.qa(text); target.messages.push({ id: nextMessageId++, role: 'assistant', text: data.answer || '未收到回答', time: now(), sources: data.sources || [] }); scrollBottom() } catch { ElMessage.error('问答请求失败，请检查后端服务') } finally { loading.value = false } }
function selectFiles(event: Event) { const input = event.target as HTMLInputElement; files.value = Array.from(input.files || []); input.value = '' }
async function submitFiles() { if (!files.value.length || loading.value) return; const selected = [...files.value]; const target = current.value; if (target.title === '新会话') target.title = selected[0].name; addMessage('user', `请根据 ${selected.length} 份材料生成文书要点摘要。`, { files: selected.map(file => file.name) }); files.value = []; loading.value = true; try { const { data } = await studioApi.land(selected); target.projectId = data.project_id || ''; target.messages.push({ id: nextMessageId++, role: 'assistant', text: data.report || '未收到报告', time: now() }); scrollBottom(); ElMessage.success('文书要点摘要已生成') } catch { ElMessage.error('文书摘要生成失败，请检查材料或后端服务') } finally { loading.value = false } }
async function review(decision: 'approved' | 'revision_required' | 'rejected') { if (!current.value.projectId) return; reviewing.value = true; try { await studioApi.review(current.value.projectId, decision); current.value.projectId = ''; ElMessage.success('人工复核结果已保存') } finally { reviewing.value = false } }
</script>
<style scoped>
.workspace{display:grid;grid-template-columns:238px minmax(0,1fr);height:calc(100vh - 92px);min-height:540px;border:1px solid #e4e9ef;border-radius:5px;background:#fff;color:#334155;overflow:hidden}.workspace.compact{grid-template-columns:56px minmax(0,1fr)}.sessions{border-right:1px solid #e4e9ef;padding:12px;min-width:0}.sessions-head{display:flex;align-items:center;justify-content:space-between;height:34px}.sessions-head strong{font-size:14px}.sessions-head small{font-size:11px;background:#eef0ff;color:#464feb;padding:2px 6px;border-radius:4px}.new-session{width:100%;justify-content:flex-start;margin:10px 0 18px}.caption{font-size:11px;color:#8793a4;margin-bottom:8px}.session{display:block;width:100%;text-align:left;border:0;background:transparent;border-radius:4px;padding:10px;cursor:pointer;color:#475569}.session:hover,.session.active{background:#edf2f7}.session.active{border-left:3px solid #464feb}.session b,.session small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.session b{font-size:13px;font-weight:500}.session small{font-size:11px;color:#94a3b8;margin-top:5px}.chat{display:flex;flex-direction:column;min-width:0}.chat-head{height:70px;flex:none;border-bottom:1px solid #e4e9ef;display:flex;justify-content:space-between;align-items:center;padding:10px 24px}.chat-head small{font-size:11px;color:#94a3b8}.chat-head h1{font-size:17px;margin:4px 0 0}.messages{flex:1;min-height:0;overflow:auto;padding:25px max(24px,calc((100% - 790px)/2))}.empty{min-height:80%;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center}.empty>.el-icon{font-size:58px;color:#a8b2c2}.empty h2{font-size:19px;margin:18px 0 5px}.empty p{max-width:480px;font-size:13px;color:#64748b;line-height:1.6}.prompts{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:18px}.prompts button{background:#fff;border:1px solid #dfe5ee;border-radius:4px;padding:9px 11px;font-size:12px;color:#475569;cursor:pointer}.prompts button:hover{color:#464feb;border-color:#464feb}.message{display:flex;gap:12px;margin-bottom:24px}.avatar{width:29px;height:29px;flex:none;display:grid;place-items:center;border-radius:5px;background:#eef0ff;color:#464feb;font-size:11px;font-weight:700}.avatar.user{background:#e8f2f7;color:#326781}.message-body{min-width:0;flex:1}.message-body b{font-size:12px}.message-body time{font-weight:400;color:#94a3b8;margin-left:8px;font-size:11px}.message-text{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.75;font-size:13px;margin-top:8px}.sources,.processing{font-size:11px;color:#64748b;margin-top:10px}.files{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.review{border-top:1px solid #e4e9ef;background:#fbfcfe;padding:9px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px}.review div{display:flex;gap:7px}.composer-area{border-top:1px solid #e4e9ef;padding:12px 24px 18px}.composer{max-width:790px;margin:auto;border:1px solid #cdd8e7;border-radius:5px;padding:8px}.composer:focus-within{border-color:#464feb}.composer textarea{width:100%;border:0;outline:0;resize:none;font:inherit;font-size:13px;padding:6px 8px}.composer-actions{display:flex;justify-content:space-between;align-items:center;color:#94a3b8;font-size:11px;padding:4px}.file-toolbar{display:flex;align-items:center;gap:10px}.file-toolbar span{font-size:11px;color:#94a3b8}.file-input{display:none}@media(max-width:760px){.workspace,.workspace.compact{display:block;height:calc(100vh - 76px);min-height:440px}.sessions{display:none}.chat{height:100%}.chat-head{padding:10px 16px;height:62px}.messages{padding:18px 14px}.composer-area{padding:10px 12px}.review{display:block;padding:10px}.review div{margin-top:8px;flex-wrap:wrap}}
</style>



