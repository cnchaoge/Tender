<template>
  <div class="settings-page">
    <el-row :gutter="20">
      <!-- AI 模型配置 -->
      <el-col :span="12">
        <el-card>
          <template #header>AI 模型配置（通义千问）</template>
          <el-form label-width="100px">
            <el-form-item label="模型">
              <el-select v-model="cfg.model" style="width: 100%">
                <el-option label="qwen-turbo（快速）" value="qwen-turbo" />
                <el-option label="qwen-plus（增强）" value="qwen-plus" />
                <el-option label="qwen-max（最强）" value="qwen-max" />
              </el-select>
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="cfg.api_key" type="password" show-password placeholder="sk-xxxxxxxx" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="v.loading" @click="verifyModel">验证</el-button>
              <el-button type="success" :disabled="!v.model_ok" :loading="saving" @click="saveModel">保存</el-button>
            </el-form-item>
            <el-form-item v-if="v.model_msg">
              <span :class="v.model_ok ? 'text-success' : 'text-error'">{{ v.model_msg }}</span>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 飞书配置 -->
        <el-card style="margin-top: 20px">
          <template #header>飞书配置</template>
          <el-form label-width="100px">
            <el-form-item label="App ID">
              <el-input v-model="cfg.feishu_app_id" placeholder="cli_xxxxxxxx" />
            </el-form-item>
            <el-form-item label="App Secret">
              <el-input v-model="cfg.feishu_app_secret" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="v.feishu_loading" @click="verifyFeishu">验证</el-button>
              <el-button type="success" :disabled="!v.feishu_ok" :loading="saving" @click="saveFeishu">保存</el-button>
            </el-form-item>
            <el-form-item v-if="v.feishu_msg">
              <span :class="v.feishu_ok ? 'text-success' : 'text-error'">{{ v.feishu_msg }}</span>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 重启服务 -->
        <el-card style="margin-top: 20px">
          <template #header>服务控制</template>
          <el-form label-width="100px">
            <el-form-item>
              <el-button type="warning" :loading="restarting" @click="restartServer">重启服务（使配置生效）</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 用户管理 -->
      <el-col :span="12">
        <el-card>
          <template #header>用户管理</template>
          <el-table :data="users" stripe size="small">
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="role" label="角色" width="80">
              <template #default="{ row }">
                <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'" size="small">
                  {{ row.role }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button type="danger" size="small" link @click="delUser(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 添加用户 -->
        <el-card style="margin-top: 20px">
          <template #header>添加用户</template>
          <el-form label-width="80px" size="small">
            <el-form-item label="用户名">
              <el-input v-model="newUser.username" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="newUser.password" type="password" show-password />
            </el-form-item>
            <el-form-item label="角色">
              <el-select v-model="newUser.role" style="width: 100%">
                <el-option label="管理员" value="admin" />
                <el-option label="普通用户" value="user" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="addUser">添加</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import api from "../api"

const users = ref([])
const saving = ref(false)
const restarting = ref(false)

const cfg = ref({
  model: "qwen-turbo",
  api_key: "",
  feishu_app_id: "",
  feishu_app_secret: ""
})

const v = ref({
  loading: false,
  model_ok: false,
  model_msg: "",
  feishu_loading: false,
  feishu_ok: false,
  feishu_msg: ""
})

const newUser = ref({ username: "", password: "", role: "user" })

onMounted(async () => {
  await loadConfig()
  const resp = await api.get("/api/admin/users")
  users.value = resp.data
})

async function loadConfig() {
  try {
    const resp = await api.get("/api/admin/config")
    cfg.value.model = resp.data.dashscope_model || "qwen-turbo"
    cfg.value.feishu_app_id = resp.data.feishu_app_id || ""
  } catch (e) {
    // ignore
  }
}

async function verifyModel() {
  if (!cfg.value.api_key) {
    ElMessage.warning("请先输入 API Key")
    return
  }
  v.value.loading = true
  v.value.model_msg = ""
  try {
    const resp = await api.post("/api/admin/model/verify", {
      api_key: cfg.value.api_key,
      model: cfg.value.model
    })
    v.value.model_ok = resp.data.valid
    v.value.model_msg = resp.data.message
    ElMessage.success(resp.data.valid ? "验证通过" : "验证失败")
  } catch (e) {
    v.value.model_ok = false
    v.value.model_msg = e.response?.data?.detail || "验证失败"
    ElMessage.error("验证失败")
  } finally {
    v.value.loading = false
  }
}

async function saveModel() {
  saving.value = true
  try {
    await api.post("/api/admin/model/config", {
      api_key: cfg.value.api_key,
      model: cfg.value.model
    })
    v.value.model_ok = false
    ElMessage.success("AI 模型配置已保存，需重启服务生效")
  } catch (e) {
    ElMessage.error("保存失败")
  } finally {
    saving.value = false
  }
}

async function verifyFeishu() {
  if (!cfg.value.feishu_app_id || !cfg.value.feishu_app_secret) {
    ElMessage.warning("请输入 App ID 和 App Secret")
    return
  }
  v.value.feishu_loading = true
  v.value.feishu_msg = ""
  try {
    const resp = await api.post("/api/admin/feishu/verify", {
      app_id: cfg.value.feishu_app_id,
      app_secret: cfg.value.feishu_app_secret
    })
    v.value.feishu_ok = resp.data.valid
    v.value.feishu_msg = resp.data.message
    ElMessage.success(resp.data.valid ? "连接成功" : "验证失败")
  } catch (e) {
    v.value.feishu_ok = false
    v.value.feishu_msg = e.response?.data?.detail || "验证失败"
    ElMessage.error("验证失败")
  } finally {
    v.value.feishu_loading = false
  }
}

async function saveFeishu() {
  saving.value = true
  try {
    await api.post("/api/admin/feishu/config", {
      app_id: cfg.value.feishu_app_id,
      app_secret: cfg.value.feishu_app_secret
    })
    v.value.feishu_ok = false
    ElMessage.success("飞书配置已保存，需重启服务生效")
  } catch (e) {
    ElMessage.error("保存失败")
  } finally {
    saving.value = false
  }
}

async function restartServer() {
  restarting.value = true
  try {
    await api.post("/api/admin/restart")
  } catch (e) {
    // 预期：进程被 kill 后请求失败
  } finally {
    setTimeout(() => { window.location.reload() }, 2000)
  }
}

async function addUser() {
  if (!newUser.value.username || !newUser.value.password) {
    ElMessage.warning("请填写用户名和密码")
    return
  }
  try {
    await api.post("/api/admin/users", newUser.value)
    const resp = await api.get("/api/admin/users")
    users.value = resp.data
    newUser.value = { username: "", password: "", role: "user" }
    ElMessage.success("添加成功")
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "添加失败")
  }
}

async function delUser(id) {
  try {
    await api.delete(`/api/admin/users/${id}`)
    const resp = await api.get("/api/admin/users")
    users.value = resp.data
    ElMessage.success("删除成功")
  } catch (e) {
    ElMessage.error("删除失败")
  }
}
</script>

<style scoped>
.text-success { color: #67c23a; }
.text-error { color: #f56c6c; }
</style>
