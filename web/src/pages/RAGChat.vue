<template>
  <div class="chat-page">
    <el-card class="chat-card">
      <template #header>
        <span>RAG 智能问答</span>
      </template>

      <!-- 消息列表 -->
      <div class="messages" ref="messagesEl">
        <div v-if="!messages.length" class="empty-tip">
          <el-icon size="40" color="#c0c4cc"><component :is="ChatDotRound" /></el-icon>
          <p>上传文档后，开始提问吧</p>
        </div>
        <div
          v-for="(msg, i) in messages"
          :key="i"
          :class="['message', msg.role]"
        >
          <div class="message-content">
            <div class="answer" v-if="msg.role === 'assistant'">{{ msg.content }}</div>
            <div class="question" v-else>{{ msg.content }}</div>
            <!-- 来源 -->
            <div v-if="msg.sources?.length" class="sources">
              <div class="sources-title">参考来源：</div>
              <div
                v-for="s in msg.sources"
                :key="s.id"
                class="source-item"
              >
                <span class="source-file">{{ s.filename }}</span>
                <span class="source-score">{{ (s.score * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="loading" class="message assistant">
          <div class="message-content">
            <el-icon class="loading-icon"><component :is="Loading" /></el-icon>
            AI 思考中...
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="input-area">
        <el-input
          v-model="question"
          placeholder="输入问题，按回车发送"
          :disabled="loading"
          @keyup.enter="send"
        >
          <template #append>
            <el-button :disabled="!question || loading" @click="send">
              <el-icon><component :is="Position" /></el-icon>
            </el-button>
          </template>
        </el-input>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, nextTick } from "vue"
import { ElMessage } from "element-plus"
import { Loading, ChatDotRound } from "@element-plus/icons-vue"
import api from "../api"

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
  loading.value = true

  try {
    const resp = await api.post("/api/rag/query", { question: q, top_k: 5 })
    messages.value.push({
      role: "assistant",
      content: resp.data.answer,
      sources: resp.data.sources
    })
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "请求失败")
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
.chat-card {
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
  max-height: calc(100vh - 280px);
}

.empty-tip {
  text-align: center;
  padding: 60px;
  color: #c0c4cc;
}

.empty-tip p {
  margin-top: 12px;
  font-size: 14px;
}

.message {
  display: flex;
  margin-bottom: 16px;
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.message-content {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 1.6;
}

.message.user .message-content {
  background: #409eff;
  color: #fff;
}

.message.assistant .message-content {
  background: #f5f7fa;
  color: #303133;
}

.sources {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(0,0,0,0.08);
}

.sources-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.source-item {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  padding: 2px 0;
  color: #606266;
}

.source-score {
  color: #67c23a;
  font-weight: bold;
}

.input-area {
  margin-top: 16px;
}
</style>
