<template>
  <div class="bid-analyze-page">

    <!-- Page Header -->
    <div class="page-header">
      <div class="eyebrow">投标工具</div>
      <h1 class="page-title">旧标书解析</h1>
      <p class="page-desc">上传历史投标标书，AI 自动拆解为结构化章节，存入知识库供新标书生成时复用</p>
    </div>

    <!-- Upload Zone -->
    <div class="upload-section">
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleFileUpload"
        accept=".pdf,.docx"
        :disabled="uploading"
      >
        <div class="upload-zone" :class="{ dragging: dragOver }" @dragover.prevent="dragOver = true" @dragleave="dragOver = false">
          <div class="upload-icon">
            <el-icon :size="24"><component :is="Upload" /></el-icon>
          </div>
          <div class="upload-text" v-if="!uploading">点击或拖拽上传历史标书文件</div>
          <div class="upload-text" v-else>正在上传...</div>
          <div class="upload-hint">支持 PDF / DOCX 格式</div>
        </div>
      </el-upload>
      <div v-if="uploading" class="progress-bar-wrap">
        <el-progress :percentage="uploadProgress" :stroke-width="6" />
      </div>
    </div>

    <!-- Divider -->
    <div class="divider">
      <span class="divider-line"></span>
      <span class="divider-text">或者从知识库选择已有文件</span>
      <span class="divider-line"></span>
    </div>

    <!-- Select Existing Document -->
    <div class="analyze-card">
      <div v-if="kbStore.documents.length">
        <div class="select-label">选择已有文件</div>
        <div class="select-row">
          <el-select v-model="selectedBidDocId" placeholder="选择历史标书文件..." style="width: 420px" filterable>
            <el-option
              v-for="doc in availableOldBids"
              :key="doc.id"
              :label="doc.filename"
              :value="doc.id"
            >
              <span>{{ doc.filename }}</span>
              <span class="bid-meta">{{ doc.file_type?.toUpperCase() }} · {{ doc.chunk_count || 0 }} 片</span>
            </el-option>
          </el-select>
          <el-button type="primary" :disabled="!selectedBidDocId" :loading="analyzingNow" @click="handleAnalyze">
            <el-icon v-if="!analyzingNow"><component :is="DataBoard" /></el-icon>
            {{ analyzingNow ? '解析中...' : '开始解析' }}
          </el-button>
        </div>
      </div>
      <div v-else class="empty-hint-text">知识库暂无文档，请先在上方上传文件</div>
    </div>

    <!-- Analyzing Progress (simulated) -->
    <div v-if="analyzingNow" class="analyzing-panel">
      <div class="analyzing-header">
        <span class="analyzing-stage">{{ analyzeStageText }}</span>
        <span class="analyzing-pct">{{ analyzeProgress }}%</span>
      </div>
      <el-progress :percentage="analyzeProgress" :stroke-width="6" status="warning" />
    </div>

    <!-- Result -->
    <div v-if="oldBidResult" class="result-card">
      <div class="result-header">
        <div class="result-icon">
          <el-icon color="#22c55e" :size="20"><component :is="Check" /></el-icon>
        </div>
        <div class="result-info">
          <div class="result-title">解析完成</div>
          <div class="result-meta">{{ oldBidResult.filename }} · 共识别 {{ oldBidResult.section_count }} 个章节</div>
        </div>
        <el-button size="small" text @click="viewAnalyzedSections(selectedBidDocId)">查看详情</el-button>
      </div>
      <div class="section-chips">
        <el-tag
          v-for="s in oldBidResult.sections"
          :key="s.section_name"
          size="small"
          :type="sectionTagType(s.section_type)"
          effect="plain"
        >
          {{ s.section_name }}
        </el-tag>
      </div>
    </div>

    <!-- Section Detail Dialog -->
    <el-dialog v-model="sectionDialogVisible" title="标书拆解详情" width="680px" :close-on-click-modal="false">
      <div v-if="analyzedSections.length" class="section-list">
        <div v-for="(sec, i) in analyzedSections" :key="i" class="section-item">
          <div class="section-header">
            <span class="section-num">{{ i + 1 }}</span>
            <el-tag size="small" :type="sectionTagType(sec.section_type)" effect="plain">
              {{ sectionTypeLabel(sec.section_type) }}
            </el-tag>
            <span class="section-name">{{ sec.section_name }}</span>
          </div>
          <div class="section-keyinfo">{{ sec.key_info }}</div>
          <div class="section-content">{{ sec.content }}</div>
        </div>
      </div>
      <div v-else class="empty-detail">暂无数据</div>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { Document, Check, DataBoard, Upload } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"
import api from "../api"

const kbStore = useKbStore()
const uploadRef = ref(null)
const dragOver = ref(false)

// Upload state
const uploading = ref(false)
const uploadProgress = ref(0)

// Analyze state
const selectedBidDocId = ref(null)
const analyzingNow = ref(false)
const analyzeProgress = ref(0)
const analyzeStageText = ref("")
const oldBidResult = ref(null)
const analyzedSections = ref([])
const sectionDialogVisible = ref(false)

onMounted(() => kbStore.fetchDocuments())

const availableOldBids = computed(() => {
  return kbStore.documents.filter(doc => {
    if (doc.filename.startsWith('bid_')) return false
    return ['.pdf', '.docx', '.doc'].some(ext => doc.filename.toLowerCase().endsWith(ext))
  })
})

function sectionTagType(type) {
  const map = {
    technical: 'primary', commercial: 'success', qualification: 'warning',
    price: 'danger', company_profile: 'info', bid_letter: '', appendix: '',
  }
  return map[type] || ''
}

function sectionTypeLabel(type) {
  const map = {
    bid_letter: '投标函', technical: '技术标', commercial: '商务标',
    qualification: '资格审查', price: '报价', company_profile: '公司介绍',
    appendix: '附录附件', other: '其他',
  }
  return map[type] || type
}

async function handleFileUpload(file) {
  const rawFile = file.raw
  if (!rawFile) return

  uploading.value = true
  uploadProgress.value = 0
  dragOver.value = false

  const interval = setInterval(() => {
    if (uploadProgress.value < 85) uploadProgress.value += 15
  }, 200)

  try {
    const formData = new FormData()
    formData.append("file", rawFile)
    const resp = await api.post("/api/kb/documents", formData, {
      headers: { "Content-Type": "multipart/form-data" }
    })
    uploadProgress.value = 100
    await kbStore.fetchDocuments()

    const docId = resp.data.doc_id
    selectedBidDocId.value = docId
    ElMessage.success("上传成功，即将开始解析...")
    uploadRef.value?.clearFiles()

    setTimeout(async () => {
      uploading.value = false
      uploadProgress.value = 0
      await triggerAnalyze(docId)
    }, 600)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "上传失败")
    uploading.value = false
    uploadProgress.value = 0
  } finally {
    clearInterval(interval)
  }
}

async function handleAnalyze() {
  if (!selectedBidDocId.value) return
  await triggerAnalyze(selectedBidDocId.value)
}

async function triggerAnalyze(docId) {
  analyzingNow.value = true
  oldBidResult.value = null
  analyzeProgress.value = 0
  analyzeStageText.value = "AI 正在分析标书结构..."

  const interval = setInterval(() => {
    if (analyzeProgress.value < 45) analyzeProgress.value += 5
  }, 300)

  try {
    setTimeout(() => { analyzeStageText.value = "正在拆解章节内容..." }, 1500)

    const resp = await api.post(`/api/bid/analyze-old/${docId}`)
    oldBidResult.value = resp.data.data

    clearInterval(interval)
    analyzeProgress.value = 100
    analyzeStageText.value = "解析完成"

    setTimeout(() => { analyzeProgress.value = 0 }, 800)
    ElMessage.success(`解析完成，共识别 ${oldBidResult.value.section_count} 个章节`)
  } catch (e) {
    clearInterval(interval)
    ElMessage.error(e.response?.data?.detail || e.response?.data?.message || "解析失败")
  } finally {
    await kbStore.fetchDocuments()
    setTimeout(() => { analyzingNow.value = false }, 400)
  }
}

async function viewAnalyzedSections(docId) {
  try {
    const resp = await api.get(`/api/bid/analyze-old/${docId}/sections`)
    analyzedSections.value = resp.data.data || []
    sectionDialogVisible.value = true
  } catch {
    ElMessage.error("获取章节详情失败")
  }
}
</script>

<style scoped>
.bid-analyze-page {
  padding: 32px 40px 64px;
  max-width: 860px;
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
  font-size: 28px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.6px;
  line-height: 1.2;
  margin-bottom: 6px;
}
.page-desc {
  font-size: 14px;
  color: var(--color-ink-subtle);
  line-height: 1.5;
}

/* ── Upload Section ── */
.upload-section {
  margin-bottom: 20px;
}
.upload-zone {
  background: var(--color-surface-1);
  border: 1px dashed var(--color-hairline-strong);
  border-radius: var(--radius-lg);
  padding: 36px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.upload-zone:hover,
.upload-zone.dragging {
  border-color: var(--color-primary);
  background: rgba(94, 105, 209, 0.04);
}
.upload-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-ink-subtle);
  margin-bottom: 2px;
}
.upload-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink);
}
.upload-hint {
  font-size: 12px;
  color: var(--color-ink-tertiary);
}
.progress-bar-wrap {
  margin-top: 12px;
  padding: 0 2px;
}

/* ── Divider ── */
.divider {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
}
.divider-line {
  flex: 1;
  height: 1px;
  background: var(--color-hairline);
}
.divider-text {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  white-space: nowrap;
}

/* ── Analyze Card ── */
.analyze-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  margin-bottom: 16px;
}
.select-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 10px;
}
.select-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.bid-meta {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  margin-left: 8px;
}
.empty-hint-text {
  text-align: center;
  padding: 16px 0;
  font-size: 13px;
  color: var(--color-ink-tertiary);
}

/* ── Analyzing Panel ── */
.analyzing-panel {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  margin-bottom: 16px;
}
.analyzing-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.analyzing-stage {
  font-size: 13px;
  color: var(--color-ink-subtle);
}
.analyzing-pct {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-semantic-warning);
}

/* ── Result ── */
.result-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
}
.result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.result-icon { flex-shrink: 0; }
.result-info { flex: 1; }
.result-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
}
.result-meta {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-top: 2px;
}
.section-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ── Section Detail Dialog ── */
.section-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 480px;
  overflow-y: auto;
}
.section-item {
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  padding: 14px;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.section-num {
  width: 22px; height: 22px;
  border-radius: 50%;
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
  color: var(--color-ink-muted);
  flex-shrink: 0;
}
.section-name {
  font-weight: 500;
  font-size: 14px;
  color: var(--color-ink);
}
.section-keyinfo {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-bottom: 8px;
  line-height: 1.5;
  padding-left: 30px;
}
.section-content {
  font-size: 12px;
  color: var(--color-ink-muted);
  background: var(--color-surface-2);
  border-radius: var(--radius-sm);
  padding: 10px;
  max-height: 160px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.6;
}
.empty-detail {
  text-align: center;
  color: var(--color-ink-tertiary);
  padding: 32px;
}
</style>
