<template>
  <div class="layout" :class="{ 'sidebar-open': mobileMenuOpen }">

    <!-- ── Top Bar (tablet/mobile) ── -->
    <header class="topbar">
      <div class="topbar-brand">
        <span class="brand-icon">⚡</span>
        <span class="brand-name">ClawOS</span>
      </div>
      <button class="hamburger" @click="mobileMenuOpen = !mobileMenuOpen" :class="{ active: mobileMenuOpen }">
        <span></span><span></span><span></span>
      </button>
    </header>

    <!-- ── Sidebar (desktop always / tablet+ mobile overlay) ── -->
    <aside class="sidebar" :class="{ 'mobile-visible': mobileMenuOpen }">
      <div class="sidebar-inner">
        <div class="sidebar-brand">
          <span class="brand-icon">⚡</span>
          <span class="brand-name">ClawOS</span>
        </div>

        <nav class="sidebar-nav">
          <div class="nav-section-label">功能</div>
          <router-link
            v-for="item in navItems"
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
          <div class="deploy-badge">
            <span class="deploy-dot"></span>
            本地部署
          </div>
          <div class="user-row" @click="handleLogout">
            <el-icon><component :is="User" /></el-icon>
            <span>{{ authStore.user?.username }}</span>
            <el-icon class="logout-icon"><component :is="SwitchButton" /></el-icon>
          </div>
        </div>
      </div>
    </aside>

    <!-- ── Overlay (tablet/mobile click-to-close) ── -->
    <div class="sidebar-overlay" v-if="mobileMenuOpen" @click="mobileMenuOpen = false" />

    <!-- ── Main Content ── -->
    <main class="main">
      <router-view />
    </main>

  </div>
</template>

<script setup>
import { ref, computed } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useAuthStore } from "../stores/auth"
import {
  Odometer, Document, ChatDotRound, Files, Setting, User, SwitchButton
} from "@element-plus/icons-vue"

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const mobileMenuOpen = ref(false)

const navItems = [
  { path: "/dashboard", label: "仪表盘", icon: Odometer },
  { path: "/kb", label: "知识库", icon: Document },
  { path: "/chat", label: "RAG 问答", icon: ChatDotRound },
  { path: "/bid", label: "标书生成", icon: Files },
  { path: "/settings", label: "系统设置", icon: Setting },
]

function isActive(path) {
  return route.path === path || route.path.startsWith(path + "/")
}

function handleLogout() {
  authStore.logout()
  router.push("/login")
}
</script>

<style scoped>
/* ── Layout Shell ── */
.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  grid-template-rows: 1fr;
  min-height: 100vh;
  background: var(--color-canvas);
}

/* ── Top Bar (hidden on desktop) ── */
.topbar {
  display: none;
}

/* ── Sidebar ── */
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
  gap: 8px;
  padding: 0 16px;
  height: 56px;
  border-bottom: 1px solid var(--color-hairline);
  flex-shrink: 0;
}
.brand-icon {
  font-size: 18px;
}
.brand-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.3px;
}

/* ── Nav ── */
.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-section-label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--color-ink-tertiary);
  padding: 4px 8px 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  text-decoration: none;
  color: var(--color-ink-subtle);
  font-size: 13px;
  font-weight: 400;
  transition: all 0.12s ease;
}
.nav-item:hover {
  background: var(--color-surface-2);
  color: var(--color-ink);
}
.nav-item.active {
  background: rgba(94, 105, 209, 0.12);
  color: var(--color-primary);
  font-weight: 500;
}
.nav-icon {
  font-size: 15px;
  flex-shrink: 0;
  width: 18px;
}
.nav-label {
  white-space: nowrap;
}

/* ── Sidebar Footer ── */
.sidebar-footer {
  padding: 12px 8px;
  border-top: 1px solid var(--color-hairline);
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

.deploy-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-brand-secure);
  padding: 4px 10px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}
.deploy-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-brand-secure);
  opacity: 0.6;
}

.user-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-ink-subtle);
  cursor: pointer;
  transition: all 0.12s;
}
.user-row:hover {
  background: var(--color-surface-2);
  color: var(--color-ink);
}
.logout-icon {
  margin-left: auto;
  font-size: 13px;
}

/* ── Main ── */
.main {
  grid-column: 2;
  grid-row: 1;
  min-height: 100vh;
  overflow-y: auto;
}

/* ── Overlay ── */
.sidebar-overlay {
  display: none;
}

/* ══════════════════════════════════════
   RESPONSIVE — Tablet (≤1024px)
   Sidebar becomes hamburger + drawer
══════════════════════════════════════ */
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
    background: var(--color-canvas);
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
    transition: background 0.15s;
  }
  .hamburger:hover,
  .hamburger.active {
    background: var(--color-surface-1);
  }
  .hamburger span {
    display: block;
    width: 18px;
    height: 1.5px;
    background: var(--color-ink);
    border-radius: 1px;
    transition: all 0.2s;
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
    width: 220px;
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
    background: rgba(0, 0, 0, 0.5);
    z-index: 90;
    backdrop-filter: blur(2px);
  }

  .main {
    grid-column: 1;
    grid-row: 2;
  }
}

/* ══════════════════════════════════════
   RESPONSIVE — Mobile (≤640px)
══════════════════════════════════════ */
@media (max-width: 640px) {
  .sidebar {
    width: 100%;
    max-width: 280px;
  }

  .brand-name {
    font-size: 14px;
  }

  .topbar {
    padding: 0 12px;
  }

  .main {
    padding: 0;
  }
}
</style>
