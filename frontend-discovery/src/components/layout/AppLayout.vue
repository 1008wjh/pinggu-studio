<template>
  <div class="app-layout" :class="{ compact: !expanded }">
    <div v-if="mobileOpen" class="mobile-scrim" @click="mobileOpen = false"></div>
    <aside class="sidebar-aside" :class="{ 'mobile-open': mobileOpen }"><Sidebar :expanded="expanded || mobileOpen" @navigate="mobileOpen = false" /></aside>
    <div class="content">
      <header class="app-header">
        <div class="header-left"><el-button text :icon="mobileOpen ? Close : Menu" class="mobile-toggle" title="打开导航" @click="mobileOpen = !mobileOpen" /><el-button text :icon="expanded ? Fold : Expand" class="desktop-toggle" :title="expanded ? '收起导航' : '展开导航'" @click="expanded = !expanded" /><span class="breadcrumb">Pinggu Studio <i>/</i> <strong>{{ pageTitle }}</strong></span></div>
        <div class="header-right"><span class="username">{{ auth.user?.username ?? auth.user?.userId }}</span><el-button text :icon="SwitchButton" title="退出登录" @click="logout">退出</el-button></div>
      </header>
      <main class="app-main"><router-view /></main>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Close, Expand, Fold, Menu, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import Sidebar from './Sidebar.vue'
const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const expanded = ref(localStorage.getItem('pinggu-nav-expanded') !== 'false')
const mobileOpen = ref(false)
watch(expanded, value => localStorage.setItem('pinggu-nav-expanded', String(value)))
const names: Record<string, string> = { studio: '工作室总览', 'studio-qa': '法律知识问答', 'studio-land': '文书要点摘要', 'document-review': '合同审查工作流', evaluation: '评测测试', knowledge: '知识库管理', workspace: '文档与表格工作台' }
const pageTitle = computed(() => names[String(route.name)] || '工作室')
function logout() { auth.logout(); router.push('/login') }
</script>
<style scoped>
.app-layout{height:100vh;display:grid;grid-template-columns:240px minmax(0,1fr);background:#f1f4f9}.app-layout.compact{grid-template-columns:64px minmax(0,1fr)}.sidebar-aside{border-right:1px solid #e5e9f0;background:#fff;min-width:0;z-index:10}.content{display:flex;flex-direction:column;min-width:0}.app-header{height:58px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 21px;border-bottom:1px solid #e5e9f0;background:#fff;box-shadow:0 1px 0 #ffffff}.header-left,.header-right{display:flex;align-items:center;gap:8px}.breadcrumb{font-size:12px;color:#768397}.breadcrumb i{font-style:normal;color:#b6becb;margin:0 7px}.breadcrumb strong{color:#334155;font-weight:600}.username{font-size:12px;color:#64748b;margin-right:8px}.app-main{flex:1;min-height:0;overflow:auto;padding:16px 20px;background:linear-gradient(135deg,#f1f4f9 0%,#f8f9fc 58%,#eef1fa 100%)}.mobile-toggle{display:none}.mobile-scrim{display:none}@media(max-width:760px){.app-layout,.app-layout.compact{display:block}.sidebar-aside{position:fixed;inset:0 auto 0 0;width:260px;transform:translateX(-100%);transition:transform .2s}.sidebar-aside.mobile-open{transform:translateX(0)}.mobile-scrim{display:block;position:fixed;inset:0;background:#0f172a66;z-index:9}.content{height:100vh}.mobile-toggle{display:inline-flex}.desktop-toggle{display:none}.app-header{padding:0 10px}.app-main{padding:8px}.username{max-width:80px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.breadcrumb{font-size:11px}}
</style>

