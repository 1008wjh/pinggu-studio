<template>
  <div class="home"><header class="home-head"><div><small>WORKSPACE OVERVIEW</small><h1>企业企业法律文档智能平台</h1><p>选择一个专业 Agent，开始处理你的工作。</p></div><el-tag effect="plain" type="success">服务正常</el-tag></header><div class="section-title">专业智能体</div><div class="cards"><button v-for="item in agents" :key="item.path" class="agent-card" @click="router.push(item.path)"><span class="agent-icon">{{ item.icon }}</span><span class="agent-copy"><b>{{ item.title }}</b><small>{{ item.desc }}</small></span><span class="arrow">→</span></button></div><div class="section-title tools-title">工作工具</div><div class="tool-row"><button @click="router.push('/knowledge')"><el-icon><Collection /></el-icon><span><b>知识库管理</b><small>维护 Agent 检索资料</small></span>→</button><button @click="router.push('/workspace')"><el-icon><FolderOpened /></el-icon><span><b>文档与表格工作台</b><small>抽取、检查与合并文件</small></span>→</button></div></div>
</template>
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Collection, FolderOpened } from '@element-plus/icons-vue'
const router = useRouter()
const agents = [{ path: '/studio/qa', icon: '✦', title: '法律知识问答', desc: '合同、招投标与企业制度知识库问答' }, { path: '/studio/land', icon: '⌖', title: '文书要点摘要', desc: '提炼文书事实、义务、风险与待办事项' }, { path: '/document-review', icon: '▤', title: '审查工作流', desc: '三步审查、人工复核和审计追踪' }]
</script>
<style scoped>
.home{max-width:1040px;margin:auto}.home-head{display:flex;justify-content:space-between;align-items:flex-start;padding:18px 0 33px}.home-head small{font-size:10px;letter-spacing:1.5px;color:#6a72dc;font-weight:700}.home-head h1{font-size:26px;letter-spacing:-.4px;margin:9px 0 7px;color:#263247}.home-head p{color:#8793a4;font-size:13px;margin:0}.section-title{font-size:12px;font-weight:700;color:#526075;margin-bottom:11px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.agent-card,.tool-row button{border:1px solid #e3e8ef;background:#fff;text-align:left;border-radius:5px;cursor:pointer}.agent-card{display:grid;grid-template-columns:42px 1fr 18px;gap:12px;align-items:center;padding:19px 15px;min-height:112px}.agent-card:hover,.tool-row button:hover{border-color:#9da5ed;box-shadow:0 7px 18px #3440540d}.agent-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:5px;background:#eef0ff;color:#555dd1;font-size:22px}.agent-card:nth-child(2) .agent-icon{background:#ecf8f5;color:#299678}.agent-card:nth-child(3) .agent-icon{background:#fff5e9;color:#ca8a31}.agent-copy b,.agent-copy small{display:block}.agent-copy b{font-size:14px;color:#334155;margin-bottom:6px}.agent-copy small{font-size:11px;color:#8c98a8;line-height:1.5}.arrow{color:#8d98a8;font-size:18px}.tools-title{margin-top:31px}.tool-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.tool-row button{display:flex;align-items:center;gap:13px;padding:15px;color:#788699;font-size:17px}.tool-row .el-icon{font-size:20px;color:#6670db}.tool-row span{display:flex;flex:1;flex-direction:column;gap:5px;text-align:left}.tool-row b{font-size:13px;color:#3c4a5e}.tool-row small{font-size:11px;color:#95a0af}@media(max-width:700px){.cards,.tool-row{grid-template-columns:1fr}.home-head h1{font-size:23px}.home-head .el-tag{display:none}}
</style>





