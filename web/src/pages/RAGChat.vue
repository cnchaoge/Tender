<template>
  <div class="chat-page">

    <div class="page-header">
      <div class="eyebrow">知识检索</div>
      <h1 class="page-title">RAG 问答</h1>
    </div>

    <div class="chat-container">
      <!-- Messages -->
      <div class="messages" ref="messagesEl">
        <div v-if="!messages.length" class="chat-empty">
          <div class="chat-empty-icon">💬</div>
          <div class="chat-empty-title">问我关于文档的问题</div>
          <div class="chat-empty-desc">上传文档后，基于知识库回答你的任何问题</div>
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="msg-row"
          :class="msg.role"
        >
          <div class="msg-avatar">
            <el-icon v-if="msg.role === 'assistant'"><component :is="MagicStick" /></el-icon>
            <el-icon v-else><component :is="User" /></el-icon>
          </div>
          <div class="msg-bubble">
            <div class="msg-text" v-html="renderMarkdown(msg.content)"></div>
            <div v-if="msg.sources?.length" class="sources">
              <div class="sources-label">参考来源</div>
              <div
                v-for="s in msg.sources"
                :key="s.id"
                class="source-item"
              >
                <span class="source-name">{{ s.filename }}</span>
                <span class="source-score">{{ (s.score * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="loading" class="msg-row assistant">
          <div class="msg-avatar">
            <el-icon><component :is="MagicStick" /></el-icon>
          </div>
          <div class="msg-bubble loading-bubble">
            <el-icon class="spin"><component :is="Loading" /></el-icon>
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
          <el-icon><component :is="Promotion" /></el-icon>
        </el-button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, nextTick } from "vue"
import { ElMessage } from "element-plus"
import { Loading, MagicStick, User, Promotion } from "@element-plus/icons-vue"
import { marked } from "marked"
import api from "../api"

// Configure marked
marked.setOptions({ breaks: true, gfm: true })

function renderMarkdown(text) {
  if (!text) return ""
  return marked.parse(text)
}

const question = ref("")
const messages = ref([])
const loading = ref(false)
const messagesEl = ref()

const _apiBase = import.meta.env.DEV
  ? ""
  : (import.meta.env.VITE_API_URL || "http://localhost:8000")

async function send() {
  if (!question.value.trim() || loading.value) return
  const q = question.value.trim()
  question.value = ""
  messages.value.push({ role: "user", content: q })
  scrollBottom()
  loading.value = true

  // 插入占位消息，流式更新
  const msgIdx = messages.value.length
  messages.value.push({ role: "assistant", content: "", sources: [] })

  try {
    const resp = await fetch(`${_apiBase}/api/rag/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, top_k: 5, stream: true }),
    })

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
        const payload = line.slice(6)
        if (payload === "[DONE]") continue

        try {
          const parsed = JSON.parse(payload)
          if (parsed.type === "sources") {
            messages.value[msgIdx].sources = parsed.content
          } else if (parsed.type === "text") {
            messages.value[msgIdx].content += parsed.content
            scrollBottom()
          }
        } catch {
          // 跳过畸形 JSON
        }
      }
    }
  } catch (e) {
    // 流式失败，降级为非流式
    try {
      const resp = await api.post("/api/rag/query", { question: q, top_k: 5 })
      messages.value[msgIdx] = {
        role: "assistant",
        content: resp.data.answer,
        sources: resp.data.sources,
      }
    } catch (e2) {
      ElMessage.error(e2.response?.data?.detail || "请求失败")
      messages.value.splice(msgIdx, 1)
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
</script>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px - 48px); /* viewport - topbar - padding */
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

/* ── Container ── */
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  overflow: hidden;
  min-height: 0;
}

/* ── Messages ── */
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

/* ── Message Row ── */
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

/* ── Markdown rendered in bubbles ── */
.msg-text :deep(p) { margin: 0 0 6px; }
.msg-text :deep(p:last-child) { margin-bottom: 0; }
.msg-text :deep(ul), .msg-text :deep(ol) { margin: 0 0 6px; padding-left: 18px; }
.msg-text :deep(li) { margin-bottom: 2px; }
.msg-text :deep(strong) { font-weight: 600; color: var(--color-ink); }
.msg-text :deep(code) { background: rgba(0,0,0,0.06); padding: 1px 5px; border-radius: 3px; font-size: 12px; font-family: var(--font-mono); }
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

/* ── Sources ── */
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

/* ── Input Bar ── */
.chat-input-bar {
  flex-shrink: 0;
  display: flex;
  gap: 8px;
  padding: 14px 16px;
  border-top: 1px solid var(--color-hairline);
  background: var(--color-surface-1);
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
@media (max-width: 640px) {
  .chat-page {
    height: calc(100vh - 56px - 32px);
  }
  .msg-bubble {
    max-width: 85%;
  }
  .source-name {
    max-width: 120px;
  }
  .messages {
    padding: 14px 12px;
  }
}
</style>
