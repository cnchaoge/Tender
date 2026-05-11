<template>
  <div class="kb-page">

    <div class="page-header">
      <div class="eyebrow">知识管理</div>
      <h1 class="page-title">知识库</h1>
    </div>

    <!-- Toolbar -->
    <div class="kb-toolbar">
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleFileChange"
        accept=".pdf,.docx,.xlsx,.xls,.pptx,.md,.txt"
      >
        <el-button type="primary">
          <el-icon><Upload /></el-icon>
          上传文件
        </el-button>
      </el-upload>
    </div>

    <!-- Table -->
    <div class="kb-table-wrap">
      <el-table
        :data="dedupedDocuments"
        v-loading="kbStore.loading"
        class="kb-table"
        row-key="id"
      >
        <el-table-column prop="filename" label="文件名" min-width="160" />
        <el-table-column prop="file_type" label="类型" width="80">
          <template #default="{ row }">
            <span class="type-badge">{{ row.file_type?.toUpperCase() }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="切片数" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <span class="status-pill" :class="row.status">
              <span class="status-dot"></span>
              {{ { ready: '就绪', processing: '处理中', error: '错误' }[row.status] || row.status }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="添加时间" width="170" />
        <el-table-column label="" width="60" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              size="small"
              text
              @click="handleDelete(row.id)"
            >
              <el-icon><component :is="Delete" /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty State -->
      <div v-if="!kbStore.documents.length && !kbStore.loading" class="empty-state">
        <div class="empty-icon">📂</div>
        <div class="empty-title">暂无文档</div>
        <div class="empty-desc">上传施工方案、标准合同等素材，构建知识库</div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, computed } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Delete, Upload } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"

const kbStore = useKbStore()
const loading = ref(false)
const uploadRef = ref(null)

// 按文件名去重（同名保留最早那条）
const dedupedDocuments = computed(() => {
  const seen = new Set()
  return kbStore.documents.filter(doc => {
    if (seen.has(doc.filename)) return false
    seen.add(doc.filename)
    return true
  })
})

onMounted(() => kbStore.fetchDocuments())

async function handleFileChange(file) {
  const rawFile = file.raw
  if (!rawFile) return
  loading.value = true
  try {
    const formData = new FormData()
    formData.append("file", rawFile)
    await kbStore.uploadDocument(formData)
    ElMessage.success("上传成功")
    uploadRef.value?.clearFiles()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "上传失败")
  } finally {
    loading.value = false
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm("确认删除此文档？", "提示", { type: "warning" })
  try {
    await kbStore.deleteDocument(id)
    ElMessage.success("删除成功")
  } catch {
    ElMessage.error("删除失败")
  }
}
</script>

<style scoped>
.kb-page {
  padding-bottom: 64px;
}

.page-header {
  margin-bottom: 24px;
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

/* ── Toolbar ── */
.kb-toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: center;
}
.folder-input {
  flex: 1;
  max-width: 380px;
}

/* ── Table ── */
.kb-table-wrap {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.kb-table {
  --el-table-bg-color: var(--color-surface-1);
  --el-table-tr-bg-color: var(--color-surface-1);
  --el-table-header-bg-color: var(--color-surface-2);
  --el-table-header-text-color: var(--color-ink-subtle);
  --el-table-text-color: var(--color-ink-muted);
  --el-table-border-color: var(--color-hairline);
  --el-table-row-hover-bg-color: var(--color-surface-2);
  font-size: 13px;
}

.type-badge {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.3px;
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  background: var(--color-surface-2);
  color: var(--color-ink-subtle);
  border: 1px solid var(--color-hairline);
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.status-pill.ready .status-dot { background: var(--color-semantic-success); }
.status-pill.processing .status-dot { background: var(--color-semantic-warning); }
.status-pill.error .status-dot { background: var(--color-semantic-error); }
.status-pill.ready { color: var(--color-semantic-success); }
.status-pill.processing { color: var(--color-semantic-warning); }
.status-pill.error { color: var(--color-semantic-error); }

/* ── Empty ── */
.empty-state {
  padding: 64px 24px;
  text-align: center;
}
.empty-icon {
  font-size: 40px;
  opacity: 0.4;
  margin-bottom: 12px;
}
.empty-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 6px;
}
.empty-desc {
  font-size: 13px;
  color: var(--color-ink-tertiary);
}

/* ── Responsive ── */
@media (max-width: 640px) {
  .kb-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .folder-input {
    max-width: 100%;
  }
  .kb-table-wrap {
    overflow-x: auto;
  }
}
</style>
