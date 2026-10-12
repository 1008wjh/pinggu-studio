<template>
  <div class="sidebar">
    <RouterLink to="/studio" class="brand" aria-label="Pinggu Studio" @click="emit('navigate')"><span class="brand-mark"><i></i><b></b></span><span v-if="expanded" class="brand-text"><b>Pinggu Studio</b><small>企业文档智能工作室</small></span></RouterLink>
    <nav class="nav">
      <RouterLink v-for="item in items" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }" :title="expanded ? '' : item.label" @click="emit('navigate')">
        <el-icon><component :is="item.icon" /></el-icon><span v-if="expanded">{{ item.label }}</span>
      </RouterLink>
    </nav>
    <div v-if="expanded" class="sidebar-foot">Pinggu Studio · 工作区</div>
  </div>
</template>
<script setup lang="ts">
import { useRoute } from 'vue-router'
import { ChatDotRound, Collection, DataAnalysis, Document, FolderOpened, House, Location } from '@element-plus/icons-vue'
defineProps<{ expanded: boolean }>()
const emit = defineEmits<{ navigate: [] }>()
const route = useRoute()
const items = [
  { path: '/studio', label: '工作室总览', icon: House },
  { path: '/studio/qa', label: '法律知识问答', icon: ChatDotRound },
  { path: '/studio/land', label: '文书要点摘要', icon: Location },
  { path: '/document-review', label: '合同审查工作流', icon: Document },
  { path: '/evaluation', label: '评测测试', icon: DataAnalysis },
  { path: '/knowledge', label: '知识库管理', icon: Collection },
  { path: '/workspace', label: '文档与表格工作台', icon: FolderOpened },
]
</script>
<style scoped>
.sidebar{height:100%;display:flex;flex-direction:column;overflow:auto}.brand{height:70px;display:flex;align-items:center;gap:10px;text-decoration:none;color:#263247;padding:0 16px;border-bottom:1px solid #e7ebf1;white-space:nowrap}.brand-mark{position:relative;width:34px;height:34px;flex:none;display:block;overflow:hidden;border-radius:9px;background:linear-gradient(145deg,#2f3fc1,#6568ef 58%,#a99aff);box-shadow:0 6px 14px #464feb3d}.brand-mark:before,.brand-mark:after,.brand-mark i,.brand-mark b{content:'';position:absolute;display:block;border-radius:3px;background:#fff}.brand-mark:before{width:4px;height:18px;left:9px;top:8px}.brand-mark:after{width:10px;height:4px;left:9px;top:8px;box-shadow:0 7px 0 #ffffff}.brand-mark i{width:11px;height:4px;right:7px;bottom:8px;transform:rotate(-28deg);background:#c9c8ff}.brand-mark b{width:4px;height:11px;right:7px;top:8px;background:#c9c8ff}.brand-text{display:flex;flex-direction:column;gap:3px;min-width:0}.brand-text b{font-size:14px}.brand-text small{font-size:10px;color:#94a3b8}.nav{padding:18px 8px;display:flex;flex-direction:column;gap:4px}.nav-item{position:relative;display:flex;align-items:center;gap:12px;min-height:40px;padding:8px 11px;border-radius:5px;color:#64748b;text-decoration:none;font-size:13px;white-space:nowrap}.nav-item .el-icon{font-size:18px;flex:none}.nav-item:hover{color:#464feb;background:#f5f7fa}.nav-item.active{color:#464feb;background:#edf2f7;font-weight:600}.nav-item.active:before{content:'';position:absolute;left:-8px;width:3px;top:6px;bottom:6px;background:#464feb;border-radius:2px}.sidebar-foot{font-size:11px;color:#a2adbc;margin:auto 16px 17px;border-top:1px solid #e7ebf1;padding-top:13px}
</style>

