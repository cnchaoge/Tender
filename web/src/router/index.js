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
    path: "/change-password",
    name: "ChangePassword",
    component: () => import("../pages/ChangePassword.vue"),
    meta: { requiresAuth: true, allowPasswordChange: true }
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
      { path: "price", name: "PriceAnalyze", component: () => import("../pages/PriceAnalyze.vue") },
      { path: "settings", name: "Settings", component: () => import("../pages/Settings.vue"), meta: { requiresAdmin: true } },
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const mustChange = !!(authStore.token && authStore.user?.must_change_password)
  if (to.meta.requiresAuth && !authStore.token) {
    next("/login")
  } else if (mustChange && !to.meta.allowPasswordChange) {
    next("/change-password")
  } else if (to.meta.allowPasswordChange && authStore.token && !mustChange) {
    next("/dashboard")
  } else if (to.matched.some(record => record.meta.requiresAdmin) && authStore.user?.role !== "admin") {
    next("/dashboard")
  } else if (to.meta.guest && authStore.token) {
    next(mustChange ? "/change-password" : "/")
  } else {
    next()
  }
})

export default router
