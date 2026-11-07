<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">
        <BrandMark />
        <div>
          <div class="logo-name">Tender</div>
          <div class="logo-sub">制造业投标写作</div>
        </div>
      </div>

      <div>
        <p class="login-title">登录</p>
        <p class="login-note">使用企业账号进入工作台</p>
      </div>

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
import BrandMark from "../components/BrandMark.vue"

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
  max-width: 400px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-top: 3px solid var(--color-primary);
  border-radius: var(--radius-md);
  padding: 32px 28px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  box-shadow: 0 2px 6px rgba(22, 22, 22, 0.06);
}

.login-logo {
  display: flex;
  align-items: center;
  gap: 12px;
}
.logo-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-ink);
  line-height: 1.2;
}
.logo-sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-ink-subtle);
}

.login-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0;
}
.login-note {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--color-ink-subtle);
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
