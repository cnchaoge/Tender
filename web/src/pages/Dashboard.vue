<template>
  <div class="dashboard-page">

    <header class="page-header">
      <div>
        <h1 class="page-title">工作台</h1>
        <p class="page-desc">总览知识库与投标写作的关键数据</p>
      </div>
      <el-button type="primary" :loading="creating" @click="createBid">新建标书</el-button>
    </header>

    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-icon"><el-icon :size="18"><Document /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-label">知识库文档</div>
          <div class="kpi-num">{{ stats.document_count ?? 0 }}</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon"><el-icon :size="18"><Files /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-label">文档切片</div>
          <div class="kpi-num">{{ stats.chunk_count ?? 0 }}</div>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-icon"><el-icon :size="18"><EditPen /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-label">投标项目</div>
          <div class="kpi-num">{{ projectTotal }}</div>
        </div>
      </div>
      <div v-if="showUserCount" class="kpi-card">
        <div class="kpi-icon"><el-icon :size="18"><User /></el-icon></div>
        <div class="kpi-body">
          <div class="kpi-label">企业用户</div>
          <div class="kpi-num">{{ stats.user_count ?? 0 }}</div>
        </div>
      </div>
    </div>

    <section class="panel">
      <div class="panel-head">
        <h2>最近项目</h2>
      </div>

      <div v-if="projectsLoading" class="panel-empty">正在加载项目…</div>
      <div v-else-if="projectsError" class="panel-empty">暂时无法加载项目</div>
      <div v-else-if="!recentProjects.length" class="panel-empty">
        还没有投标项目。从「新建标书」开始。
      </div>
      <div v-else class="table-wrap">
        <table class="activity-table">
          <thead>
            <tr>
              <th>项目名称</th>
              <th>状态</th>
              <th>工期</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in recentProjects" :key="row.id">
              <td class="name-cell">{{ row.name || "未命名项目" }}</td>
              <td>{{ statusLabel(row.status) }}</td>
              <td>{{ row.deadline || "—" }}</td>
              <td class="time-cell">{{ formatTime(row.updated_at || row.created_at) }}</td>
              <td>
                <router-link :to="projectLink(row.id)" class="row-link">打开</router-link>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="unlinkedRows.length" class="panel">
      <div class="panel-head">
        <h2>未归入项目</h2>
      </div>
      <div class="table-wrap">
        <table class="activity-table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in unlinkedRows" :key="row.key">
              <td class="name-cell">{{ row.name || "未命名" }}</td>
              <td>{{ row.kind }}</td>
              <td class="time-cell">{{ formatTime(row.time) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="shortcuts">
      <router-link v-for="item in shortcuts" :key="item.path" :to="item.path" class="shortcut">
        <el-icon class="shortcut-icon"><component :is="item.icon" /></el-icon>
        <span class="shortcut-body">
          <span class="shortcut-title">{{ item.title }}</span>
          <span class="shortcut-desc">{{ item.desc }}</span>
        </span>
      </router-link>
    </section>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import api from "../api"
import { listProjects } from "../features/projects/api"
import { useAuthStore } from "../stores/auth"
import { useWorkspaceStore } from "../stores/workspace"
import {
  Document, Files, EditPen, User, DataAnalysis, Histogram, Collection, ChatDotRound,
} from "@element-plus/icons-vue"

const router = useRouter()
const authStore = useAuthStore()
const workspace = useWorkspaceStore()
const stats = ref({ document_count: 0, chunk_count: 0, user_count: 0 })
const showUserCount = ref(false)
const projects = ref([])
const unlinked = ref({ versions: [], prices: [] })
const projectsLoading = ref(true)
const projectsError = ref(false)
const creating = ref(false)

const statusText = { draft: "草稿", active: "进行中", archived: "已归档" }

const shortcuts = [
  { path: "/bid", title: "标书生成", desc: "按招标要求编写投标文件", icon: EditPen },
  { path: "/bid-analyze", title: "标书解析", desc: "提取技术要求与评分标准", icon: DataAnalysis },
  { path: "/price", title: "报价分析", desc: "核算评分公式与报价", icon: Histogram },
  { path: "/kb", title: "知识库", desc: "管理企业文档与素材", icon: Collection },
  { path: "/chat", title: "智能问答", desc: "基于知识库检索并回答", icon: ChatDotRound },
]

const recentProjects = computed(() => projects.value.slice(0, 8))
const projectTotal = computed(() => projects.value.length)
const unlinkedRows = computed(() => {
  const versions = (unlinked.value.versions || []).map((row) => ({
    key: `v-${row.id}`,
    name: row.project_name,
    kind: "标书版本",
    time: row.generated_at,
  }))
  const prices = (unlinked.value.prices || []).map((row) => ({
    key: `p-${row.id}`,
    name: row.project_name,
    kind: "报价",
    time: row.created_at,
  }))
  return [...versions, ...prices]
})

function statusLabel(status) {
  return statusText[status] || status || "—"
}

function projectLink(id) {
  return { path: "/bid", query: { project_id: String(id) } }
}

async function createBid() {
  if (creating.value) return
  creating.value = true
  try {
    const project = await workspace.createProject({})
    router.push(projectLink(project.id))
  } catch {
    ElMessage.error("创建项目失败")
  } finally {
    creating.value = false
  }
}

function formatTime(value) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").slice(0, 16)
  const pad = (n) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(async () => {
  projectsLoading.value = true
  try {
    const resp = await listProjects()
    projects.value = resp.data?.projects || []
    unlinked.value = resp.data?.unlinked || { versions: [], prices: [] }
  } catch {
    projectsError.value = true
  } finally {
    projectsLoading.value = false
  }

  if (authStore.user?.role === "admin") {
    try {
      const resp = await api.get("/api/admin/stats")
      stats.value = resp.data
      showUserCount.value = true
    } catch {}
    return
  }
  try {
    const resp = await api.get("/api/kb/documents")
    const docs = resp.data || []
    stats.value = {
      document_count: docs.length,
      chunk_count: docs.reduce((sum, doc) => sum + (doc.chunk_count || 0), 0),
      user_count: 0,
    }
  } catch {}
})
</script>

<style scoped>
.dashboard-page {
  padding: 0 0 32px;
  max-width: 1180px;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--color-ink);
  line-height: 1.25;
}

.page-desc {
  margin-top: 4px;
  font-size: 13px;
  color: var(--color-ink-subtle);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.kpi-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  padding: 16px;
  min-height: 84px;
}

.kpi-icon {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: var(--color-primary);
  color: #fff;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}

.kpi-label {
  font-size: 12px;
  color: var(--color-ink-subtle);
}

.kpi-num {
  margin-top: 2px;
  font-size: 24px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: 0;
  line-height: 1.2;
}

.panel {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-hairline);
}

.panel-head h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
}

.panel-link,
.row-link {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-primary);
}

.panel-link:hover,
.row-link:hover {
  color: var(--color-primary-hover);
}

.panel-empty {
  padding: 28px 16px;
  text-align: center;
  color: var(--color-ink-subtle);
  font-size: 13px;
}

.table-wrap {
  overflow-x: auto;
}

.activity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.activity-table th {
  text-align: left;
  font-weight: 500;
  color: var(--color-ink-muted);
  background: var(--color-surface-2);
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-hairline);
  white-space: nowrap;
}

.activity-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-hairline);
  color: var(--color-ink);
  vertical-align: middle;
}

.activity-table tbody tr:last-child td {
  border-bottom: 0;
}

.activity-table tbody tr:hover td {
  background: #edf5ff;
}

.name-cell {
  font-weight: 500;
}

.time-cell {
  color: var(--color-ink-muted);
  white-space: nowrap;
}

.shortcuts {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.shortcut {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  color: inherit;
  min-height: 84px;
}

.shortcut:hover {
  border-color: var(--color-primary);
  background: #f8fbff;
}

.shortcut-icon {
  color: var(--color-primary);
  font-size: 16px;
  margin-top: 2px;
}

.shortcut-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.shortcut-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ink);
}

.shortcut-desc {
  font-size: 12px;
  line-height: 1.4;
  color: var(--color-ink-subtle);
}

@media (max-width: 1100px) {
  .shortcuts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .dashboard-page {
    padding: 0 0 24px;
  }
  .page-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .kpi-grid,
  .shortcuts {
    grid-template-columns: 1fr;
  }
}
</style>
