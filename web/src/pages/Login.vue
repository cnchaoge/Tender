<template>
  <div class="login-layout">

    <!-- Left Hero Panel -->
    <div class="hero-panel">
      <div class="hero-inner">
        <div class="hero-brand">
          <span class="brand-icon">⚡</span>
          <span class="brand-name">ClawOS X</span>
        </div>
        <h1 class="hero-headline">制造业投标标书<br>AI 一键生成</h1>
        <p class="hero-sub">上传产品资料 / 选择标书模板 / 生成专业投标文件</p>

        <div class="hero-features">
          <div class="feature-item">
            <span class="feature-check">✓</span>
            <span>数据本地存储，文件不离开工厂</span>
          </div>
          <div class="feature-item">
            <span class="feature-check">✓</span>
            <span>开箱即用，无需复杂配置</span>
          </div>
          <div class="feature-item">
            <span class="feature-check">✓</span>
            <span>行业垂直，专为制造业定制</span>
          </div>
        </div>

        <div class="hero-footer">
          已有 <strong>127</strong> 家工厂正在使用
        </div>
      </div>
    </div>

    <!-- Right Login Panel -->
    <div class="login-panel">
      <div class="login-card">
        <!-- Logo -->
        <div class="login-logo">
          <div class="logo-icon">⚡</div>
          <div class="logo-text">
            <div class="logo-name">ClawOS X</div>
            <div class="logo-sub">智能投标标书系统</div>
          </div>
        </div>

        <p class="login-title">欢迎回来</p>
        <p class="login-hint">登录以进入控制台</p>

        <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
          <el-form-item prop="username">
            <el-input
              v-model="form.username"
              placeholder="用户名"
              size="large"
              :prefix-icon="User"
            />
          </el-form-item>
          <el-form-item prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="密码"
              size="large"
              :prefix-icon="Lock"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form>

        <div class="login-tips">默认账号：admin / admin123</div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { User, Lock } from "@element-plus/icons-vue"
import { useAuthStore } from "../stores/auth"

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({ username: "admin", password: "admin123" })
const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }]
}

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authStore.login(form.username, form.password)
    router.push("/dashboard")
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "登录失败")
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ── Two-column layout ── */
.login-layout {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1fr 1fr;
}

/* ── Hero Panel ── */
.hero-panel {
  background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  position: relative;
  overflow: hidden;
}

.hero-panel::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -30%;
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}

.hero-panel::after {
  content: '';
  position: absolute;
  bottom: -40%;
  left: -20%;
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(255,255,255,0.05) 0%, transparent 70%);
  border-radius: 50%;
  pointer-events: none;
}

.hero-inner {
  max-width: 400px;
  position: relative;
  z-index: 1;
}

.hero-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 40px;
}
.brand-icon {
  font-size: 28px;
}
.brand-name {
  font-size: 22px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.5px;
}

.hero-headline {
  font-size: 36px;
  font-weight: 700;
  color: #fff;
  line-height: 1.2;
  letter-spacing: -1px;
  margin-bottom: 16px;
}

.hero-sub {
  font-size: 15px;
  color: rgba(255,255,255,0.75);
  line-height: 1.6;
  margin-bottom: 36px;
}

.hero-features {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 40px;
}
.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: rgba(255,255,255,0.9);
}
.feature-check {
  color: #86EFAC;
  font-weight: 600;
  font-size: 15px;
}

.hero-footer {
  font-size: 13px;
  color: rgba(255,255,255,0.6);
  padding-top: 24px;
  border-top: 1px solid rgba(255,255,255,0.2);
}
.hero-footer strong {
  color: #fff;
}

/* ── Login Panel ── */
.login-panel {
  background: var(--color-canvas);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 32px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Logo ── */
.login-logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.logo-icon {
  font-size: 28px;
}
.logo-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.logo-name {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-ink);
  letter-spacing: -0.4px;
}
.logo-sub {
  font-size: 12px;
  color: var(--color-ink-subtle);
  letter-spacing: 0.3px;
}

.login-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.4px;
  margin-bottom: 0;
}

.login-hint {
  font-size: 13px;
  color: var(--color-ink-subtle);
  margin-top: -8px;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 15px !important;
  font-weight: 500 !important;
  margin-top: 8px;
}

.login-tips {
  text-align: center;
  color: var(--color-ink-tertiary);
  font-size: 12px;
  margin-top: -4px;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .login-layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }

  .hero-panel {
    padding: 36px 24px 28px;
  }

  .hero-inner {
    max-width: 100%;
  }

  .hero-brand {
    margin-bottom: 24px;
  }

  .hero-headline {
    font-size: 26px;
    margin-bottom: 12px;
  }

  .hero-features {
    margin-bottom: 24px;
  }

  .hero-footer {
    display: none;
  }

  .login-panel {
    padding: 32px 24px;
    align-items: flex-start;
  }

  .login-logo {
    display: flex;
  }
}
</style>