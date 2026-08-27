import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'home', component: HomeView },
    {
      path: '/contracts',
      name: 'contracts',
      component: () => import('../views/ContractsView.vue'),
    },
    {
      path: '/contracts/:id',
      name: 'contract-detail',
      component: () => import('../views/ContractDetailView.vue'),
    },
    {
      path: '/documents/:id',
      name: 'results',
      component: () => import('../views/ResultsView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.initialized) await auth.restore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) return { name: 'home' }
    return true
  }
  if (!auth.isAuthenticated) return { name: 'login' }
  return true
})

export default router
