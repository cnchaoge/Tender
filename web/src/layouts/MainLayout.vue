<template>
  <div class="layout" :class="{ 'sidebar-open': mobileMenuOpen }">

    <header class="topbar">
      <div class="topbar-brand">
        <BrandMark />
        <span class="brand-name">Tender</span>
      </div>
      <button class="hamburger" @click="mobileMenuOpen = !mobileMenuOpen" :class="{ active: mobileMenuOpen }" aria-label="打开菜单">
        <span></span><span></span><span></span>
      </button>
    </header>

    <aside class="sidebar" :class="{ 'mobile-visible': mobileMenuOpen }">
      <div class="sidebar-inner">
        <div class="sidebar-brand">
          <BrandMark />
          <div class="brand-text">
            <span class="brand-name">Tender</span>
            <span class="brand-sub">制造业投标写作</span>
          </div>
        </div>

        <nav class="sidebar-nav" aria-label="主导航">
          <div class="nav-section-label">工作</div>
          <router-link
            v-for="item in primaryNav"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
            @click="mobileMenuOpen = false"
          >
            <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
            <span class="nav-label">{{ item.label }}</span>
          </router-link>
        </nav>

        <div class="sidebar-footer">
          <div class="nav-section-label">系统</div>
          <router-link
            v-if="isAdmin"
            to="/settings"
            class="nav-item"
            :class="{ active: isActive('/settings') }"
            @click="mobileMenuOpen = false"
          >
            <el-icon class="nav-icon"><Setting /></el-icon>
            <span class="nav-label">系统设置</span>
          </router-link>
          <a class="nav-item help-link" href="/docs/" target="_blank" rel="noopener" title="使用说明，含本地部署">
            <el-icon class="nav-icon"><Reading /></el-icon>
            <span class="nav-label">使用说明</span>
          </a>

          <button type="button" class="user-row" @click="handleLogout" title="退出登录">
            <span class="user-avatar">{{ initials }}</span>
            <span class="user-meta">
              <span class="user-name">{{ authStore.user?.username }}</span>
              <span class="user-role">{{ roleLabel }}</span>
            </span>
            <el-icon class="logout-icon"><SwitchButton /></el-icon>
          </button>
        </div>
      </div>
    </aside>

    <div class="sidebar-overlay" v-if="mobileMenuOpen" @click="mobileMenuOpen = false" />

    <main class="main">
      <router-view />
    </main>

  </div>
</template>

<script setup>
import { ref, computed } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useAuthStore } from "../stores/auth"
import BrandMark from "../components/BrandMark.vue"
import {
  House, EditPen, DataAnalysis, Histogram, Collection, ChatDotRound,
  Setting, SwitchButton, Reading,
} from "@element-plus/icons-vue"

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const mobileMenuOpen = ref(false)

const primaryNav = [
  { path: "/dashboard", label: "工作台", icon: House },
  { path: "/bid", label: "标书生成", icon: EditPen },
  { path: "/bid-analyze", label: "标书解析", icon: DataAnalysis },
  { path: "/price", label: "报价分析", icon: Histogram },
  { path: "/kb", label: "知识库", icon: Collection },
  { path: "/chat", label: "智能问答", icon: ChatDotRound },
]

const isAdmin = computed(() => authStore.user?.role === "admin")
const roleLabel = computed(() => (isAdmin.value ? "管理员" : "企业用户"))
const initials = computed(() => {
  const name = (authStore.user?.username || "").trim()
  return (name.slice(0, 2) || "用户").toUpperCase()
})

function isActive(path) {
  return route.path === path || route.path.startsWith(path + "/")
}

function handleLogout() {
  authStore.logout()
  router.push("/login")
}
</script>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 232px 1fr;
  grid-template-rows: 1fr;
  min-height: 100vh;
  background: var(--color-canvas);
}

.topbar {
  display: none;
}

.sidebar {
  grid-column: 1;
  grid-row: 1;
  position: sticky;
  top: 0;
  height: 100vh;
  background: var(--color-surface-1);
  border-right: 1px solid var(--color-hairline);
  overflow: hidden;
  z-index: 50;
}

.sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  height: 64px;
  border-bottom: 1px solid var(--color-hairline);
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: 0;
  line-height: 1.2;
}

.brand-sub {
  font-size: 11px;
  color: var(--color-ink-subtle);
  line-height: 1.3;
}

.sidebar-nav {
  flex: 1;
  padding: 12px 0 8px;
  display: flex;
  flex-direction: column;
}

.nav-section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-ink-subtle);
  padding: 8px 16px 6px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 1px 12px;
  padding: 9px 12px;
  border-radius: var(--radius-md);
  text-decoration: none;
  color: #393939;
  font-size: 14px;
  font-weight: 400;
}

.nav-item:hover {
  background: var(--color-surface-2);
  color: var(--color-ink);
}

.nav-item.active {
  background: var(--color-primary-wash);
  color: var(--color-primary);
  font-weight: 600;
}

.nav-item.active::before {
  content: "";
  position: absolute;
  left: -12px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  background: var(--color-primary);
}

.nav-icon {
  font-size: 16px;
  flex-shrink: 0;
  width: 18px;
}

.nav-label {
  white-space: nowrap;
}

.sidebar-footer {
  padding: 8px 0 12px;
  border-top: 1px solid var(--color-hairline);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.help-link {
  color: #393939;
}

.user-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 12px 0;
  padding: 8px;
  border: 0;
  border-top: 1px solid var(--color-hairline);
  border-radius: 0;
  background: transparent;
  font: inherit;
  text-align: left;
  color: var(--color-ink);
  cursor: pointer;
  width: calc(100% - 24px);
}

.user-row:hover {
  background: var(--color-surface-2);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  background: #d0e2ff;
  color: #0043ce;
  font-size: 12px;
  font-weight: 600;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-role {
  font-size: 11px;
  color: var(--color-ink-subtle);
}

.logout-icon {
  margin-left: auto;
  font-size: 14px;
  color: var(--color-ink-subtle);
}

.main {
  grid-column: 2;
  grid-row: 1;
  min-height: 100vh;
  min-width: 0;
  overflow-y: auto;
  background: var(--color-canvas);
  padding: 24px 28px 28px;
}

.sidebar-overlay {
  display: none;
}

@media (max-width: 1024px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: 56px 1fr;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px;
    background: var(--color-surface-1);
    border-bottom: 1px solid var(--color-hairline);
    position: sticky;
    top: 0;
    z-index: 60;
    grid-column: 1;
    grid-row: 1;
  }

  .topbar-brand {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .hamburger {
    display: flex;
    flex-direction: column;
    gap: 5px;
    background: none;
    border: none;
    cursor: pointer;
    padding: 8px;
    border-radius: var(--radius-md);
  }

  .hamburger:hover,
  .hamburger.active {
    background: var(--color-surface-2);
  }

  .hamburger span {
    display: block;
    width: 18px;
    height: 1.5px;
    background: var(--color-ink);
    transition: transform 0.2s, opacity 0.2s;
  }

  .hamburger.active span:nth-child(1) {
    transform: translateY(6.5px) rotate(45deg);
  }

  .hamburger.active span:nth-child(2) {
    opacity: 0;
  }

  .hamburger.active span:nth-child(3) {
    transform: translateY(-6.5px) rotate(-45deg);
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    height: 100vh;
    width: 232px;
    transform: translateX(-100%);
    transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 100;
    grid-column: 1;
    grid-row: 1;
  }

  .sidebar.mobile-visible {
    transform: translateX(0);
  }

  .sidebar-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(22, 22, 22, 0.45);
    z-index: 90;
  }

  .main {
    grid-column: 1;
    grid-row: 2;
    min-height: 0;
    padding: 16px;
  }
}

@media (max-width: 640px) {
  .sidebar {
    width: min(280px, 88vw);
  }

  .topbar {
    padding: 0 12px;
  }
}
</style>
