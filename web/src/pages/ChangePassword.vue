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

      <p class="login-title">设置新密码</p>
      <p class="login-note">继续使用前需要先更换当前密码。</p>

      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleSubmit">
        <el-form-item prop="oldPassword">
          <el-input
            v-model="form.oldPassword"
            type="password"
            placeholder="当前密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item prop="newPassword">
          <el-input
            v-model="form.newPassword"
            type="password"
            placeholder="新密码（至少 8 位）"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="确认新密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          class="login-btn"
          :loading="loading"
          @click="handleSubmit"
        >
          保存并继续
        </el-button>
        <p v-if="errorMsg" class="login-error">{{ errorMsg }}</p>
      </el-form>

      <button type="button" class="logout-link" @click="handleLogout">退出登录</button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { Lock } from "@element-plus/icons-vue"
import { useAuthStore } from "../stores/auth"
import BrandMark from "../components/BrandMark.vue"

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref()
const loading = ref(false)
const errorMsg = ref("")

const form = reactive({
  oldPassword: "",
  newPassword: "",
  confirmPassword: "",
})

const rules = {
  oldPassword: [{ required: true, message: "请输入当前密码", trigger: "blur" }],
  newPassword: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { min: 8, message: "新密码至少 8 位", trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: "请再次输入新密码", trigger: "blur" },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.newPassword) {
          callback(new Error("两次输入的新密码不一致"))
        } else {
          callback()
        }
      },
      trigger: "blur",
    },
  ],
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  errorMsg.value = ""
  try {
    await authStore.changePassword(form.oldPassword, form.newPassword)
    ElMessage.success("密码已更新")
    router.push("/dashboard")
  } catch (e) {
    const detail = e.response?.data?.detail
    errorMsg.value = typeof detail === "string" ? detail : "修改密码失败"
    ElMessage.error(errorMsg.value)
  } finally {
    loading.value = false
  }
}

function handleLogout() {
  authStore.logout()
  router.push("/login")
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
  font-size: 20px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.4px;
  margin: 0;
}

.login-note {
  margin: -8px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-ink-tertiary);
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

.logout-link {
  border: 0;
  background: transparent;
  color: var(--color-ink-tertiary);
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}
</style>
