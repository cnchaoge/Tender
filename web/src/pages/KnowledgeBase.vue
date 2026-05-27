<template>
  <div class="kb-page">

    <!-- Page Header -->
    <div class="page-header">
      <div class="eyebrow">知识管理</div>
      <h1 class="page-title">知识库</h1>
    </div>

    <div class="kb-layout">

      <!-- ── LEFT: Document List ── -->
      <div class="kb-sidebar">
        <div class="kb-sidebar-header">
          <span class="kb-sidebar-title">文档列表</span>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="handleFileChange"
            accept=".pdf,.docx,.xlsx,.xls,.pptx,.md,.txt,.jpg,.jpeg,.png"
            :disabled="uploading"
          >
            <el-button type="primary" size="small" :loading="uploading">
              <el-icon v-if="!uploading"><Upload /></el-icon>
              上传
            </el-button>
          </el-upload>
        </div>

        <!-- Upload progress -->
        <div v-if="uploading" class="upload-progress">
          <el-progress :percentage="uploadProgress" :stroke-width="4" />
        </div>

        <!-- Document count -->
        <div class="kb-doc-count" v-if="kbStore.documents.length">
          共 {{ kbStore.documents.length }} 个文档
        </div>

        <!-- Document list -->
        <div class="kb-doc-list" v-loading="kbStore.loading">
          <div
            v-for="doc in dedupedDocuments"
            :key="doc.id"
            class="kb-doc-item"
            :class="{ active: activeDocId === doc.id }"
            @click="selectDoc(doc)"
          >
            <div class="kb-doc-icon">
              <el-icon><Document /></el-icon>
            </div>
            <div class="kb-doc-body">
              <div class="kb-doc-name" :title="doc.filename">{{ doc.filename }}</div>
              <div class="kb-doc-meta">
                <span class="type-tag">{{ doc.file_type?.toUpperCase() }}</span>
                <span class="status-dot" :class="doc.status"></span>
                <span class="status-text">{{ statusLabel(doc.status) }}</span>
              </div>
            </div>
            <el-button
              type="danger"
              size="small"
              text
              @click.stop="handleDelete(doc.id)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>

          <!-- Empty state -->
          <div v-if="!kbStore.documents.length && !kbStore.loading" class="kb-doc-empty">
            <div class="empty-icon">📂</div>
            <div class="empty-text">知识库为空</div>
            <el-button type="primary" size="small" @click="focusUpload" class="empty-upload-btn">
              <el-icon><Upload /></el-icon>
              上传文档
            </el-button>
          </div>
        </div>
      </div>

      <!-- ── RIGHT: RAG Chat ── -->
      <div class="kb-main">
        <div class="chat-container">
          <!-- Messages -->
          <div class="messages" ref="messagesEl">
            <div v-if="!messages.length" class="chat-empty">
              <div class="chat-empty-icon">💬</div>
              <div class="chat-empty-title">问我关于文档的问题</div>
              <div class="chat-empty-desc">基于知识库回答你的任何问题</div>
            </div>

            <div
              v-for="(msg, i) in messages"
              :key="i"
              class="msg-row"
              :class="msg.role"
            >
              <div class="msg-avatar">
                <el-icon v-if="msg.role === 'assistant'"><MagicStick /></el-icon>
                <el-icon v-else><User /></el-icon>
              </div>
              <div class="msg-bubble">
                <div class="msg-text" v-html="renderMarkdown(msg.content)"></div>
                <div v-if="msg.sources?.length" class="sources">
                  <div class="sources-label">参考来源</div>
                  <div
                    v-for="s in msg.sources"
                    :key="s.doc_id || s.chunk_index"
                    class="source-item"
                    @click="selectDocById(s.doc_id)"
                  >
                    <span class="source-name">{{ s.filename }}</span>
                    <span class="source-score">{{ (s.score * 100).toFixed(1) }}%</span>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="loading" class="msg-row assistant">
              <div class="msg-avatar">
                <el-icon><MagicStick /></el-icon>
              </div>
              <div class="msg-bubble loading-bubble">
                <el-icon class="spin"><Loading /></el-icon>
                AI 思考中...
              </div>
            </div>
          </div>

          <!-- Input -->
          <div class="chat-input-bar">
            <el-input
              v-model="question"
              placeholder="输入问题，按回车发送..."
              :disabled="loading"
              @keyup.enter="send"
              class="chat-input"
            />
            <el-button
              type="primary"
              :disabled="!question.trim() || loading"
              @click="send"
              class="send-btn"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Delete, Upload, Document, MagicStick, User, Promotion, Loading } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"
import { marked } from "marked"
import api from "../api"

marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text) {
  if (!text) return ""
  return marked.parse(text)
}

const kbStore = useKbStore()

// ── Document list ──
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadRef = ref(null)
const activeDocId = ref(null)

const dedupedDocuments = computed(() => {
  const seen = new Set()
  return kbStore.documents.filter(doc => {
    if (seen.has(doc.filename)) return false
    seen.add(doc.filename)
    return true
  })
})

function statusLabel(status) {
  return { ready: '就绪', processing: '处理中', error: '错误' }[status] || status
}

function selectDoc(doc) {
  activeDocId.value = doc.id
}

function selectDocById(docId) {
  activeDocId.value = docId
  const el = document.querySelector(`.kb-doc-item[data-id="${docId}"]`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function focusUpload() {
  uploadRef.value?.$el?.querySelector('input')?.click()
}

async function handleFileChange(file) {
  const rawFile = file.raw
  if (!rawFile) return
  uploading.value = true
  uploadProgress.value = 0
  const interval = setInterval(() => {
    if (uploadProgress.value < 85) uploadProgress.value += 15
  }, 200)
  try {
    const formData = new FormData()
    formData.append("file", rawFile)
    await kbStore.uploadDocument(formData)
    uploadProgress.value = 100
    ElMessage.success("上传成功")
    uploadRef.value?.clearFiles()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "上传失败")
  } finally {
    clearInterval(interval)
    uploading.value = false
    uploadProgress.value = 0
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm("确认删除此文档？", "提示", { type: "warning" })
  try {
    await kbStore.deleteDocument(id)
    if (activeDocId.value === id) activeDocId.value = null
    ElMessage.success("删除成功")
  } catch {
    ElMessage.error("删除失败")
  }
}

// ── RAG Chat ──
const question = ref("")
const messages = ref([])
const loading = ref(false)
const messagesEl = ref()

async function send() {
  if (!question.value.trim() || loading.value) return
  const q = question.value.trim()
  question.value = ""

  messages.value.push({ role: "user", content: q })
  scrollBottom()

  const msgIdx = messages.value.length
  messages.value.push({ role: "assistant", content: "", sources: [] })
  loading.value = true

  try {
    const token = localStorage.getItem("token") || ""
    const resp = await fetch("/api/rag/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ question: q, top_k: 5, stream: true }),
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() || ""

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        const data = line.slice(6).trim()
        if (data === "[DONE]") continue

        try {
          const parsed = JSON.parse(data)
          if (parsed.type === "text") {
            messages.value[msgIdx].content += parsed.content
            scrollBottom()
          } else if (parsed.type === "sources") {
            messages.value[msgIdx].sources = parsed.content
          }
        } catch {
          // 忽略解析不完整的行
        }
      }
    }
  } catch (e) {
    // 流式失败则移除占位消息，用非流式重试
    messages.value.pop()
    loading.value = true
    try {
      const resp = await api.post("/api/rag/query", { question: q, top_k: 5, stream: false })
      messages.value.push({
        role: "assistant",
        content: resp.data.answer,
        sources: resp.data.sources,
      })
    } catch {
      ElMessage.error("请求失败")
    }
  } finally {
    loading.value = false
    scrollBottom()
  }
}

function scrollBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

onMounted(() => kbStore.fetchDocuments())
</script>

<style scoped>
.kb-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px - 40px); /* viewport - topbar - page padding */
  padding-bottom: 0;
}

.page-header {
  flex-shrink: 0;
  margin-bottom: 16px;
}
.eyebrow {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: var(--color-primary);
  margin-bottom: 4px;
}
.page-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.4px;
}

/* ── Split Layout ── */
.kb-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 0;
  min-height: 0;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

/* ── Left: Document List ── */
.kb-sidebar {
  border-right: 1px solid var(--color-hairline);
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--color-surface-2);
}

.kb-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-hairline);
  flex-shrink: 0;
}
.kb-sidebar-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ink);
}

.kb-doc-count {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  padding: 6px 16px;
  flex-shrink: 0;
}

.kb-doc-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kb-doc-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.1s;
  border: 1px solid transparent;
}
.kb-doc-item:hover {
  background: var(--color-surface-1);
}
.kb-doc-item.active {
  background: var(--color-surface-1);
  border-color: var(--color-primary);
}

.kb-doc-icon {
  flex-shrink: 0;
  color: var(--color-primary);
  font-size: 16px;
  padding-top: 2px;
}

.kb-doc-body {
  flex: 1;
  min-width: 0;
}
.kb-doc-name {
  font-size: 12px;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}
.kb-doc-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
}

.type-tag {
  font-weight: 600;
  color: var(--color-ink-subtle);
  background: var(--color-surface-1);
  padding: 1px 4px;
  border-radius: 3px;
  border: 1px solid var(--color-hairline);
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}
.status-dot.ready { background: var(--color-semantic-success); }
.status-dot.processing { background: var(--color-semantic-warning); }
.status-dot.error { background: var(--color-semantic-error); }

.status-text {
  color: var(--color-ink-tertiary);
}

/* Upload progress */
.upload-progress {
  padding: 8px 16px;
  flex-shrink: 0;
}

/* Empty state */
.kb-doc-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 16px;
  text-align: center;
}
.empty-icon { font-size: 32px; opacity: 0.3; }
.empty-text { font-size: 13px; color: var(--color-ink-subtle); }
.empty-upload-btn { margin-top: 4px; }

/* ── Right: Chat ── */
.kb-main {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* Messages */
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  text-align: center;
  padding: 40px 20px;
}
.chat-empty-icon { font-size: 40px; opacity: 0.4; }
.chat-empty-title { font-size: 15px; font-weight: 500; color: var(--color-ink); }
.chat-empty-desc { font-size: 13px; color: var(--color-ink-tertiary); }

/* Message Row */
.msg-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.msg-row.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--color-ink-subtle);
  flex-shrink: 0;
  margin-top: 2px;
}
.msg-row.assistant .msg-avatar {
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.2);
  color: var(--color-primary);
}

.msg-bubble {
  max-width: 72%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg-text {
  padding: 10px 14px;
  border-radius: var(--radius-lg);
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.msg-row.assistant .msg-text {
  background: var(--color-surface-2);
  color: var(--color-ink);
  border-bottom-left-radius: 4px;
}
.msg-row.user .msg-text {
  background: var(--color-primary);
  color: #fff;
  border-bottom-right-radius: 4px;
}

/* Markdown rendering */
.msg-text :deep(p) { margin: 0 0 6px; }
.msg-text :deep(p:last-child) { margin-bottom: 0; }
.msg-text :deep(ul), .msg-text :deep(ol) { margin: 0 0 6px; padding-left: 18px; }
.msg-text :deep(li) { margin-bottom: 2px; }
.msg-text :deep(strong) { font-weight: 600; color: var(--color-ink); }
.msg-text :deep(code) { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.msg-text :deep(pre) { background: rgba(0,0,0,0.06); padding: 8px 10px; border-radius: 6px; overflow-x: auto; margin: 4px 0; }
.msg-text :deep(pre code) { background: none; padding: 0; }
.msg-text :deep(blockquote) { border-left: 3px solid rgba(59,130,246,0.4); margin: 4px 0; padding: 2px 10px; color: var(--color-ink-subtle); }
.msg-text :deep(table) { border-collapse: collapse; width: 100%; font-size: 12px; margin-bottom: 6px; }
.msg-text :deep(th), .msg-text :deep(td) { border: 1px solid var(--color-hairline); padding: 4px 8px; text-align: left; }
.msg-text :deep(th) { background: var(--color-surface-3); font-weight: 500; }
.msg-text :deep(h1), .msg-text :deep(h2), .msg-text :deep(h3) { font-weight: 600; margin: 0 0 4px; }
.msg-text :deep(h1) { font-size: 15px; }
.msg-text :deep(h2) { font-size: 14px; }
.msg-text :deep(h3) { font-size: 13px; }

.loading-bubble {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--color-surface-2);
  color: var(--color-ink-subtle);
  font-size: 14px;
  border-radius: var(--radius-lg);
  border-bottom-left-radius: var(--radius-xs);
}

.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Sources */
.sources {
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  padding: 10px 12px;
}
.sources-label {
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--color-ink-tertiary);
  margin-bottom: 6px;
}
.source-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  padding: 3px 0;
  cursor: pointer;
  transition: color 0.1s;
}
.source-item:hover .source-name {
  color: var(--color-primary);
}
.source-name {
  color: var(--color-ink-subtle);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
.source-score {
  color: var(--color-primary);
  font-weight: 500;
  font-size: 11px;
  flex-shrink: 0;
}

/* Input Bar */
.chat-input-bar {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
  padding: 14px 16px;
  border-top: 1px solid var(--color-hairline);
  align-items: center;
}

.chat-input {
  flex: 1;
}

.send-btn {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  padding: 0 !important;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .kb-page {
    height: calc(100vh - 56px - 32px);
  }

  .kb-layout {
    grid-template-columns: 1fr;
  }

  .kb-sidebar {
    display: none;
  }

  .msg-bubble {
    max-width: 85%;
  }

  .source-name {
    max-width: 120px;
  }
}
</style>
