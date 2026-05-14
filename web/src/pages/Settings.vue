<template>
  <div class="settings-page">

    <div class="page-header">
      <div class="eyebrow">系统</div>
      <h1 class="page-title">设置</h1>
    </div>

    <div class="settings-grid">

      <!-- AI 模型配置 -->
      <div class="settings-card">
        <div class="card-title">
          AI 模型配置
          <span v-if="currentModelName" class="model-name-tag">{{ currentModelName }}</span>
        </div>
        <el-form v-if="editingModel || !currentModelName" label-position="top" class="settings-form">
          <el-form-item label="提供商">
            <el-select v-model="cfg.provider" style="width: 100%">
              <el-option label="DeepSeek" value="deepseek" />
              <el-option label="通义千问" value="dashscope" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型">
            <el-select v-if="cfg.provider === 'deepseek'" v-model="cfg.model" style="width: 100%">
              <el-option label="deepseek-chat" value="deepseek-chat" />
              <el-option label="deepseek-coder" value="deepseek-coder" />
            </el-select>
            <el-select v-else v-model="cfg.model" style="width: 100%">
              <el-option label="qwen-turbo（快速）" value="qwen-turbo" />
              <el-option label="qwen-plus（增强）" value="qwen-plus" />
              <el-option label="qwen-max（最强）" value="qwen-max" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input
              v-model="cfg.api_key"
              type="password"
              show-password
              placeholder="sk-xxxxxxxx"
            />
          </el-form-item>
          <el-form-item v-if="v.model_msg" class="verify-msg">
            <span :class="v.model_ok ? 'text-success' : 'text-error'">{{ v.model_msg }}</span>
          </el-form-item>
          <el-form-item class="form-actions">
            <el-button type="primary" :loading="v.loading" @click="verifyModel">验证</el-button>
            <el-button :disabled="!v.model_ok" :loading="saving" @click="saveModel">保存</el-button>
            <el-button type="info" @click="cancelModelEdit">取消</el-button>
          </el-form-item>
        </el-form>
        <div v-else class="form-actions">
          <el-button type="primary" @click="editingModel = true">修改</el-button>
          <el-button type="warning" :loading="restarting" @click="restartServer">重启服务</el-button>
        </div>
      </div>

      <!-- Embedding 模型配置 -->
      <div class="settings-card">
        <div class="card-title">
          Embedding 模型
          <span v-if="currentEmbedName" class="model-name-tag">{{ currentEmbedName }}</span>
        </div>
        <el-form v-if="editingEmbed || !currentEmbedName" label-position="top" class="settings-form">
          <el-form-item label="向量模型">
            <el-select v-model="cfg.embed_provider" style="width: 100%">
              <el-option label="通义千问（云，1024维）" value="dashscope" />
              <el-option label="BGE-large（本地，384维）" value="bge" />
              <el-option label="M3E-base（本地，768维）" value="m3e" />
              <el-option label="Mock（仅开发测试）" value="mock" />
            </el-select>
          </el-form-item>
          <div class="embed-hint">
            <span v-if="cfg.embed_provider === 'bge' || cfg.embed_provider === 'm3e'">
              本地模型，需联网下载。切换后需重启服务并等待模型加载。
            </span>
            <span v-else-if="cfg.embed_provider === 'dashscope'">
              云端 API，消耗通义千问 token 额度。
            </span>
            <span v-else>
              仅本地测试使用，不调真实 API。
            </span>
          </div>
          <el-form-item class="form-actions">
            <el-button type="primary" :loading="saving" @click="saveEmbed">保存</el-button>
            <el-button type="info" @click="cancelEmbedEdit">取消</el-button>
          </el-form-item>
        </el-form>
        <div v-else class="form-actions">
          <el-button type="primary" @click="editingEmbed = true">修改</el-button>
        </div>
      </div>

      <!-- 用户管理 -->
      <div class="settings-card">
        <div class="card-title">用户管理</div>
        <el-table :data="users" size="small" class="users-table" row-key="id">
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="role" label="角色" width="100">
            <template #default="{ row }">
              <span v-if="!editingId || editingId !== row.id" class="role-tag" :class="row.role">{{ row.role }}</span>
              <el-select v-else v-model="editUser.role" size="small" style="width: 90px">
                <el-option label="管理员" value="admin" />
                <el-option label="普通用户" value="user" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="160" fixed="right">
            <template #default="{ row }">
              <template v-if="editingId === row.id">
                <el-button type="primary" size="small" text @click="submitEdit(row.id)">保存</el-button>
                <el-button size="small" text @click="cancelEdit">取消</el-button>
              </template>
              <template v-else>
                <el-button type="default" size="small" text @click="startEdit(row)">编辑</el-button>
                <el-button type="danger" size="small" text @click="delUser(row.id)">删除</el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>

        <!-- 添加用户（链接展开） -->
        <div class="add-user-toggle" v-if="!showAddUser" @click="showAddUser = true">
          + 添加用户
        </div>
        <div class="add-user" v-else>
          <div class="add-user-title">添加用户</div>
          <div class="add-user-form">
            <el-input v-model="newUser.username" placeholder="用户名" />
            <el-input v-model="newUser.password" type="password" show-password placeholder="密码" />
            <el-select v-model="newUser.role" style="width: 130px">
              <el-option label="管理员" value="admin" />
              <el-option label="普通用户" value="user" />
            </el-select>
            <el-button type="primary" @click="addUser">添加</el-button>
            <el-button size="small" text @click="showAddUser = false; newUser = { username: '', password: '', role: 'user' }">取消</el-button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import api from "../api"

const users = ref([])
const saving = ref(false)
const restarting = ref(false)

const cfg = ref({ provider: "deepseek", model: "deepseek-chat", api_key: "", embed_provider: "dashscope" })
const editingModel = ref(false)
const editingEmbed = ref(false)
const currentModelName = ref("")
const currentEmbedName = ref("")

const v = ref({ loading: false, model_ok: false, model_msg: "" })

const newUser = ref({ username: "", password: "", role: "user" })
const showAddUser = ref(false)
const editingId = ref(null)
const editUser = ref({ username: "", role: "user" })

onMounted(async () => {
  await loadConfig()
  try {
    const resp = await api.get("/api/admin/users")
    users.value = resp.data
  } catch {}
})

async function loadConfig() {
  try {
    const resp = await api.get("/api/admin/config")
    cfg.value.provider = resp.data.llm_provider || "deepseek"
    cfg.value.model = resp.data.llm_provider === "deepseek"
      ? (resp.data.deepseek_model || "deepseek-chat")
      : (resp.data.dashscope_model || "qwen-turbo")
    cfg.value.embed_provider = resp.data.embed_provider || "mock"
    currentModelName.value = cfg.value.model
    currentEmbedName.value = cfg.value.embed_provider
    editingModel.value = false
    editingEmbed.value = false
  } catch {}
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
      provider: cfg.value.provider,
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
      provider: cfg.value.provider,
      api_key: cfg.value.api_key,
      model: cfg.value.model,
      embed_provider: cfg.value.embed_provider
    })
    v.value.model_ok = false
    editingModel.value = false
    currentModelName.value = cfg.value.model
    ElMessage.success("AI 模型配置已保存，需重启服务生效")
  } catch (e) {
    ElMessage.error("保存失败")
  } finally {
    saving.value = false
  }
}

function cancelModelEdit() {
  editingModel.value = false
  loadConfig()
}

async function saveEmbed() {
  saving.value = true
  try {
    await api.post("/api/admin/embed/config", {
      embed_provider: cfg.value.embed_provider
    })
    editingEmbed.value = false
    currentEmbedName.value = cfg.value.embed_provider
    ElMessage.success("Embedding 配置已保存，需重启服务生效")
  } catch (e) {
    console.error("saveEmbed error:", e.response?.data || e.message)
    ElMessage.error("保存失败")
  } finally {
    saving.value = false
  }
}

function cancelEmbedEdit() {
  editingEmbed.value = false
  loadConfig()
}

async function restartServer() {
  restarting.value = true
  try {
    await api.post("/api/admin/restart")
  } catch {
    // expected: request fails after process kill
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
  } catch {
    ElMessage.error("删除失败")
  }
}

function startEdit(row) {
  editingId.value = row.id
  editUser.value = { username: row.username, role: row.role }
}

function cancelEdit() {
  editingId.value = null
}

async function submitEdit(id) {
  try {
    await api.put(`/api/admin/users/${id}`, { role: editUser.value.role })
    const resp = await api.get("/api/admin/users")
    users.value = resp.data
    editingId.value = null
    ElMessage.success("保存成功")
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "保存失败")
  }
}
</script>

<style scoped>
.settings-page {
  padding-bottom: 64px;
}

.page-header {
  margin-bottom: 28px;
}
.eyebrow {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--color-primary);
  margin-bottom: 6px;
}
.page-title {
  font-size: 26px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.5px;
}

/* ── Grid ── */
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.settings-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 20px;
}
.settings-card.full-width {
  grid-column: 1 / -1;
}

.card-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-hairline);
  display: flex;
  align-items: center;
  gap: 10px;
}
.model-name-tag {
  font-size: 11px;
  font-weight: 500;
  background: rgba(59, 130, 246, 0.1);
  color: var(--color-primary);
  border: 1px solid rgba(59, 130, 246, 0.2);
  padding: 2px 8px;
  border-radius: var(--radius-xs);
}

/* ── Form ── */
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

.verify-msg {
  font-size: 13px;
  margin: 0;
}

.text-success { color: var(--color-semantic-success); }
.text-error { color: var(--color-semantic-error); }

/* ── Action Row ── */
.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.action-hint {
  font-size: 12px;
  color: var(--color-ink-tertiary);
}

/* ── Users Table ── */
.users-table {
  --el-table-bg-color: var(--color-surface-1);
  --el-table-tr-bg-color: var(--color-surface-1);
  --el-table-header-bg-color: var(--color-surface-2);
  --el-table-header-text-color: var(--color-ink-subtle);
  --el-table-text-color: var(--color-ink-muted);
  --el-table-border-color: var(--color-hairline);
  margin-bottom: 16px;
}

.role-tag {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-xs);
}
.role-tag.admin {
  background: rgba(245, 108, 108, 0.1);
  color: var(--color-semantic-error);
  border: 1px solid rgba(245, 108, 108, 0.2);
}
.role-tag.user {
  background: rgba(94, 105, 209, 0.1);
  color: var(--color-primary);
  border: 1px solid rgba(94, 105, 209, 0.2);
}

/* ── Add User ── */
.add-user-toggle {
  font-size: 13px;
  color: var(--color-primary);
  cursor: pointer;
  padding-top: 4px;
  user-select: none;
}
.add-user-toggle:hover {
  color: var(--color-primary-hover);
}

.add-user {
  border-top: 1px solid var(--color-hairline);
  padding-top: 16px;
}
.add-user-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 10px;
}
.add-user-form {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
  .settings-card.full-width {
    grid-column: 1;
  }
}

@media (max-width: 640px) {
  .add-user-form {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
