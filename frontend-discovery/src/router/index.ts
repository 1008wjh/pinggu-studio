import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/', component: () => import('@/components/layout/AppLayout.vue'), meta: { requiresAuth: true }, children: [
      { path: '', redirect: '/studio' },
      { path: 'studio', name: 'studio', component: () => import('@/views/StudioHomeView.vue') },
      { path: 'studio/qa', name: 'studio-qa', component: () => import('@/views/StudioQAView.vue') },
      { path: 'studio/land', name: 'studio-land', component: () => import('@/views/StudioLandView.vue') },
      { path: 'document-review', name: 'document-review', component: () => import('@/views/DocumentReviewView.vue') },
      { path: 'evaluation', name: 'evaluation', component: () => import('@/views/EvaluationView.vue') },
      { path: 'knowledge', name: 'knowledge', component: () => import('@/views/KnowledgeView.vue') },
      { path: 'workspace', name: 'workspace', component: () => import('@/views/WorkspaceView.vue') },
    ] },
    { path: '/:pathMatch(.*)*', redirect: '/studio' },
  ],
})
router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()
  if (to.meta.public) return auth.isLoggedIn && to.name === 'login' ? next('/studio') : next()
  if (!auth.isLoggedIn) return next('/login')
  next()
})
export default router



