import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "../stores/auth"

const routes = [
  {
    path: "/login",
    name: "Login",
    component: () => import("../pages/Login.vue"),
    meta: { guest: true }
  },
  {
    path: "/",
    component: () => import("../layouts/MainLayout.vue"),
    meta: { requiresAuth: true },
    children: [
      { path: "", redirect: "/dashboard" },
      { path: "dashboard", name: "Dashboard", component: () => import("../pages/Dashboard.vue") },
      { path: "kb", name: "KnowledgeBase", component: () => import("../pages/KnowledgeBase.vue") },
      { path: "chat", name: "RAGChat", component: () => import("../pages/RAGChat.vue") },
      { path: "bid", name: "BidGenerate", component: () => import("../pages/BidGenerate.vue") },
      { path: "bid-analyze", name: "BidAnalyze", component: () => import("../pages/BidAnalyze.vue") },
      { path: "settings", name: "Settings", component: () => import("../pages/Settings.vue") },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.token) {
    next("/login")
  } else if (to.meta.guest && authStore.token) {
    next("/")
  } else {
    next()
  }
})

export default router
