import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
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
