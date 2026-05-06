<template>
  <el-container class="main-layout">
    <!-- 侧边栏 -->
    <el-aside width="220px">
      <div class="logo">ClawOS X</div>
      <el-menu
        :default-active="$route.path"
        router
        background-color="#1a1a2e"
        text-color="#a0a0b0"
        active-text-color="#409eff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><component :is="Odometer" /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/kb">
          <el-icon><component :is="Document" /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><component :is="ChatDotRound" /></el-icon>
          <span>RAG 问答</span>
        </el-menu-item>
        <el-menu-item index="/bid">
          <el-icon><component :is="Files" /></el-icon>
          <span>标书生成</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><component :is="Setting" /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶部 -->
      <el-header>
        <div class="header-left">
          <span class="page-title">{{ pageTitle }}</span>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-icon><component :is="User" /></el-icon>
              {{ authStore.user?.username }}
              <el-icon class="el-icon--right"><component :is="ArrowDown" /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from "vue"
import { useRouter } from "vue-router"
import { useAuthStore } from "../stores/auth"
import { Odometer, Document, ChatDotRound, Files, Setting, User, ArrowDown } from "@element-plus/icons-vue"

const router = useRouter()
const authStore = useAuthStore()

const pageTitle = computed(() => {
  const map = {
    "/dashboard": "仪表盘",
    "/kb": "知识库",
    "/chat": "RAG 问答",
    "/bid": "标书生成",
    "/settings": "系统设置"
  }
  return map[router.currentRoute.value.path] || ""
})

function handleCommand(cmd) {
  if (cmd === "logout") {
    authStore.logout()
    router.push("/login")
  }
}
</script>

<style scoped>
.main-layout {
  height: 100vh;
}

.el-aside {
  background: #1a1a2e;
  overflow-x: hidden;
}

.logo {
  height: 60px;
  line-height: 60px;
  text-align: center;
  font-size: 18px;
  font-weight: bold;
  color: #409eff;
  border-bottom: 1px solid #2a2a3e;
}

.el-header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e8e8e8;
  padding: 0 20px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #606266;
  font-size: 14px;
}

.el-main {
  padding: 20px;
  overflow-y: auto;
}
</style>
