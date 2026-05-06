<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="title">ClawOS X</h1>
      <p class="subtitle">制造业 AI 文档助手</p>

      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            size="large"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="tips">默认账号：admin / admin123</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
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
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}

.login-card {
  background: #fff;
  border-radius: 12px;
  padding: 40px;
  width: 380px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.title {
  text-align: center;
  font-size: 28px;
  font-weight: bold;
  color: #1a1a2e;
  margin-bottom: 4px;
}

.subtitle {
  text-align: center;
  color: #909399;
  margin-bottom: 32px;
  font-size: 14px;
}

.tips {
  text-align: center;
  color: #c0c4cc;
  font-size: 12px;
  margin-top: 8px;
}
</style>
