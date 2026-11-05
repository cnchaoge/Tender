<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <div class="logo-icon">⚡</div>
        <div class="logo-name">Tender</div>
      </div>

      <p class="login-title">登录</p>

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
        <p v-if="errorMsg" class="login-error">{{ errorMsg }}</p>
      </el-form>
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
const errorMsg = ref("")

const form = reactive({ username: "", password: "" })
const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }]
}

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  errorMsg.value = ""
  try {
    const data = await authStore.login(form.username, form.password)
    if (data.user?.must_change_password || data.must_change_password) {
      router.push("/change-password")
    } else {
      router.push("/dashboard")
    }
  } catch (e) {
    const detail = e.response?.data?.detail
    errorMsg.value = typeof detail === "string" ? detail : "登录失败"
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-canvas);
  padding: 24px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-xl);
  padding: 40px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-icon {
  font-size: 28px;
}
.logo-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-ink);
  letter-spacing: -0.5px;
}

.login-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.4px;
  margin: 0;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 500;
}

.login-error {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.4;
  color: var(--color-danger, #d03050);
  text-align: center;
}
</style>
