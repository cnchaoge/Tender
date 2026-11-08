<template>
  <section class="panel">
    <div class="panel-head">
      <h2>生成作业</h2>
    </div>
    <div v-if="loading" class="panel-empty">正在查看进行中的生成…</div>
    <div v-else-if="error" class="panel-empty">暂时无法读取作业</div>
    <div v-else-if="!rows.length" class="panel-empty">没有进行中的标书生成。关掉页面后，未完成的生成会停在已经写好的章节。</div>
    <div v-else class="table-wrap">
      <table class="activity-table">
        <thead>
          <tr>
            <th>状态</th>
            <th>进度</th>
            <th>说明</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td>{{ statusText(row.status) }}</td>
            <td>{{ row.progress }}%</td>
            <td class="name-cell">{{ row.message || "—" }}</td>
            <td>
              <router-link v-if="row.project_id" :to="projectLink(row.project_id)" class="row-link">打开项目</router-link>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from "vue"
import { listJobs } from "./client"

const rows = ref([])
const loading = ref(true)
const error = ref(false)
let timer = null

const labels = {
  queued: "排队中",
  running: "生成中",
  cancelled: "已停止",
  interrupted: "已中断",
  failed: "失败",
  succeeded: "已完成",
}

function statusText(status) {
  return labels[status] || status
}

function projectLink(id) {
  return { path: "/bid", query: { project_id: String(id) } }
}

async function refresh() {
  try {
    const active = await listJobs({ type: "bid.generate", status: "queued,running", limit: 8 })
    const stopped = await listJobs({ type: "bid.generate", status: "cancelled,interrupted", limit: 8 })
    const inflight = active.jobs || []
    const recentStopped = (stopped.jobs || []).slice(0, Math.max(0, 8 - inflight.length))
    rows.value = inflight.length ? [...inflight, ...recentStopped] : recentStopped
    error.value = false
    if (inflight.length && !timer) {
      timer = setInterval(refresh, 4000)
    }
    if (!inflight.length && timer) {
      clearInterval(timer)
      timer = null
    }
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
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
.panel-empty {
  padding: 28px 16px;
  text-align: center;
  color: var(--color-ink-subtle);
  font-size: 13px;
}
.table-wrap { overflow-x: auto; }
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
}
.activity-table td {
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-hairline);
  color: var(--color-ink);
}
.activity-table tbody tr:last-child td { border-bottom: 0; }
.row-link {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-primary);
}
.name-cell { font-weight: 500; }
</style>
