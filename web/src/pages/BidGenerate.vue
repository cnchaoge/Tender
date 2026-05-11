<template>
  <div class="bid-page">

    <!-- Page Header -->
    <div class="page-header">
      <div class="eyebrow">投标工具</div>
      <h1 class="page-title">标书生成</h1>
      <p class="page-desc">上传招标文件，系统自动解析项目信息并生成完整投标标书</p>
    </div>

    <!-- Main Grid: Left = 招标文件 | Right = 素材 + 生成 -->
    <div class="bid-grid">

      <!-- ── LEFT: 招标文件 ── -->
      <div class="section">
        <div class="section-label">招标文件</div>

        <!-- Upload Zone -->
        <div class="upload-zone" @click="triggerUpload" v-if="!bidFile">
          <div class="upload-icon">
            <el-icon><component :is="Upload" /></el-icon>
          </div>
          <div class="upload-text">点击上传招标文件</div>
          <div class="upload-hint">支持 PDF / DOCX 格式</div>
          <input
            ref="fileInputRef"
            type="file"
            accept=".pdf,.docx"
            style="display: none"
            @change="onFileSelected"
          />
        </div>

        <!-- File Loaded -->
        <div class="file-card" v-if="bidFile">
          <div class="file-card-inner">
            <div class="file-icon">
              <el-icon><component :is="Document" /></el-icon>
            </div>
            <div class="file-meta">
              <div class="file-name">{{ bidFile.name }}</div>
              <div class="file-status" v-if="parseResult">已解析 · {{ Math.round(parseResult.parse_meta?.confidence * 100) }}% 可信度</div>
              <div class="file-status uploading" v-else>解析中...</div>
            </div>
            <div class="file-actions">
              <el-button size="small" @click="triggerUpload">重新上传</el-button>
            </div>
          </div>
        </div>

        <!-- Parsed Result -->
        <div v-if="parseResult && parseResult.project_name !== '解析失败'" class="parsed-section">

          <!-- Health Check Strip -->
          <div v-if="parseResult.parse_meta?.health_check?.checks?.length" class="health-strip">
            <span
              v-for="check in parseResult.parse_meta.health_check.checks"
              :key="check.item"
              class="health-item"
              :class="check.result"
            >
              <span class="health-dot"></span>
              {{ check.item }}
            </span>
          </div>

          <!-- Project Name (large, editable) -->
          <div class="field-group">
            <div class="field-label">项目名称</div>
            <div v-if="!editingProjectName" class="field-value large clickable-underline" @click="editingProjectName = true">
              {{ parseResult.project_name }}
            </div>
            <el-input
              v-else
              v-model="parseResult.project_name"
              class="field-input"
              size="large"
              @blur="editingProjectName = false"
              @keyup.enter="editingProjectName = false"
              ref="projectNameInput"
            />
          </div>

          <!-- Deadline -->
          <div class="field-group">
            <div class="field-label">工期</div>
            <div v-if="!editingDeadline" class="field-value clickable-underline" @click="editingDeadline = true">
              {{ parseResult.deadline || '未提取到' }}
            </div>
            <el-input
              v-else
              v-model="parseResult.deadline"
              class="field-input"
              @blur="editingDeadline = false"
              @keyup.enter="editingDeadline = false"
            />
          </div>

          <!-- Requirements -->
          <div class="field-group">
            <div class="field-label">资格要求</div>
            <div class="tag-list">
              <el-tag
                v-for="(r, i) in parseResult.requirements"
                :key="i"
                closable
                @close="parseResult.requirements.splice(i, 1)"
              >{{ r }}</el-tag>
              <el-input
                class="tag-add-input"
                size="small"
                placeholder="回车新增"
                @keyup.enter="e => { if(e.target.value.trim()) { parseResult.requirements.push(e.target.value.trim()); e.target.value = '' } }"
              />
            </div>
          </div>

          <!-- Qualification -->
          <div class="field-group">
            <div class="field-label">资质要求</div>
            <div class="tag-list">
              <el-tag
                v-for="(r, i) in parseResult.qualification"
                :key="i"
                closable
                type="success"
                @close="parseResult.qualification.splice(i, 1)"
              >{{ r }}</el-tag>
              <el-input
                class="tag-add-input"
                size="small"
                placeholder="回车新增"
                @keyup.enter="e => { if(e.target.value.trim()) { parseResult.qualification.push(e.target.value.trim()); e.target.value = '' } }"
              />
            </div>
          </div>

          <!-- Raw Text Toggle -->
          <div v-if="parseResult.raw_text" class="raw-toggle">
            <button class="raw-toggle-btn" @click="showRawText = !showRawText">
              <span>原文内容</span>
              <el-icon class="toggle-arrow" :class="{ open: showRawText }"><component :is="ArrowRight" /></el-icon>
            </button>
            <div v-if="showRawText" class="raw-content">
              {{ parseResult.raw_text }}
            </div>
          </div>

        </div>
      </div>

      <!-- ── RIGHT: 素材选择 + 生成 ── -->
      <div class="section">

        <!-- 素材选择 -->
        <div class="section-label">素材选择</div>
        <div class="materials-card">
          <div v-if="availableMaterials.length" class="material-list">
            <div
              v-for="mat in availableMaterials"
              :key="mat.id"
              class="material-item"
              :class="{ selected: selectedMaterials.includes(mat.id), 'match-low': getMatchInfo(mat.id)?.level === 'low' }"
              @click="toggleMaterial(mat.id)"
            >
              <el-checkbox :value="mat.id" :model-value="selectedMaterials.includes(mat.id)" />
              <div class="material-info">
                <div class="material-name">{{ mat.filename }}</div>
                <div class="material-meta">
                  <span class="meta-badge">{{ mat.file_type?.toUpperCase() }}</span>
                  <span v-if="mat.chunk_count" class="meta-chunks">{{ mat.chunk_count }} 个切片</span>
                  <!-- 匹配度分数（match_check 返回） -->
                  <span v-if="getMatchInfo(mat.id)" class="meta-score" :class="matchScoreClass(getMatchInfo(mat.id).level)">
                    匹配度 {{ getMatchInfo(mat.id).score }}%
                  </span>
                  <!-- RAG 推荐相关度（原有字段） -->
                  <span v-else-if="mat.relevance_score != null" class="meta-score" :class="scoreClass(mat.relevance_score)">
                    相关度 {{ Math.round((1 - Math.abs(mat.relevance_score)) * 100) }}%
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div class="empty-materials" v-else>
            <div class="empty-icon">📄</div>
            <div class="empty-text">知识库暂无文档</div>
            <div class="empty-hint">上传施工方案、标准合同等素材，系统将自动关联</div>
          </div>

          <!-- 内联上传区 -->
          <div class="inline-upload-area" v-if="showUploadInline">
            <el-upload
              ref="inlineUploadRef"
              :auto-upload="false"
              :show-file-list="false"
              :on-change="handleInlineFileSelected"
              accept=".pdf,.docx,.xlsx,.xls,.pptx,.md,.txt"
            >
              <el-button type="default" size="small" :loading="uploadingInline">
                <el-icon><component :is="Upload" /></el-icon>
                {{ uploadingInline ? '上传中...' : '确认上传' }}
              </el-button>
            </el-upload>
            <el-button size="small" @click="showUploadInline = false" style="margin-left: 8px">取消</el-button>
          </div>

          <!-- 素材操作栏 -->
          <div class="materials-footer">
            <el-button size="small" type="default" @click="showUploadInline = !showUploadInline">
              <el-icon><component :is="Plus" /></el-icon>
              {{ showUploadInline ? '取消' : '新增素材' }}
            </el-button>
            <el-button
              v-if="selectedMaterials.length && parseResult"
              size="small"
              type="default"
              :loading="checkingMatch"
              @click="checkMatch"
            >
              <el-icon><component :is="Files" /></el-icon>
              检测匹配度
            </el-button>
          </div>

          <!-- 匹配度汇总 -->
          <div v-if="matchCheckResult" class="match-summary" :class="matchCheckResult.warning ? 'has-warning' : ''">
            <div class="match-summary-title">
              匹配度检测结果
              <span class="match-avg">{{ matchCheckResult.summary.avg_score }}%</span>
            </div>
            <div class="match-bars">
              <span class="bar-label high">高 {{ matchCheckResult.summary.high }}个</span>
              <span class="bar-label mid">中 {{ matchCheckResult.summary.mid }}个</span>
              <span class="bar-label low">低 {{ matchCheckResult.summary.low }}个</span>
            </div>
            <div v-if="matchCheckResult.warning" class="match-warning">
              <el-icon><component :is="ArrowRight" /></el-icon>
              {{ matchCheckResult.warning }}
            </div>
          </div>
        </div>

        <!-- 生成标书 -->
        <div class="section-label" style="margin-top: 28px">生成</div>
        <div class="generate-card">
          <el-button
            type="primary"
            class="generate-btn"
            :loading="generating"
            :disabled="!parseResult || selectedMaterials.length === 0"
            @click="handleGenerate"
          >
            <el-icon v-if="!generating"><component :is="Files" /></el-icon>
            生成投标标书
          </el-button>

          <!-- Generating State -->
          <div v-if="generating" class="generating-panel">
            <div class="gen-progress-header">
              <span class="gen-stage">{{ progressMessage }}</span>
              <span class="gen-pct">{{ progress }}%</span>
            </div>
            <div class="gen-progress-bar">
              <div class="gen-progress-fill" :style="{ width: progress + '%' }"></div>
            </div>
            <!-- Streaming Preview -->
            <div class="streaming-preview" v-if="streamingContent">
              <div class="streaming-header">实时输出</div>
              <div class="streaming-text">{{ streamingContent }}</div>
            </div>
          </div>

          <!-- Done: Download -->
          <div v-if="generatedFile && !generating" class="done-panel">
            <div class="done-badge">
              <el-icon><component :is="Check" /></el-icon>
              标书已生成
            </div>
            <a :href="generatedFile.url" target="_blank" class="download-btn">
              <el-icon><component :is="Download" /></el-icon>
              下载 {{ generatedFile.name }}
            </a>
          </div>

          <!-- Done: Review -->
          <div v-if="reviewResult && !generating" class="review-panel">
            <div class="review-header">
              <span class="review-score">{{ reviewResult.score }}分</span>
              <span class="review-status" :class="reviewResult.passed ? 'pass' : 'fail'">
                {{ reviewResult.passed ? '审核通过' : '存在问题' }}
              </span>
            </div>
            <ul v-if="reviewResult.issues?.length" class="review-issues">
              <li v-for="issue in reviewResult.issues" :key="issue">{{ issue }}</li>
            </ul>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { Upload, Document, Files, Check, Download, ArrowRight, Plus } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"
import api from "../api"

const kbStore = useKbStore()
const bidFile = ref(null)
const bidDocId = ref(null)  // 上传的招标文件 doc_id，不参与素材选择
const parseResult = ref(null)
const selectedMaterials = ref([])
const generating = ref(false)
const generatedFile = ref(null)
const reviewResult = ref(null)
const progress = ref(0)
const progressMessage = ref("")
const streamingContent = ref("")
const editingProjectName = ref(false)
const editingDeadline = ref(false)
const showRawText = ref(false)
const fileInputRef = ref(null)
const showUploadInline = ref(false)  // 内联上传区展开
const uploadingInline = ref(false)
const inlineUploadRef = ref(null)
const matchCheckResult = ref(null)  // 匹配度检测结果
const checkingMatch = ref(false)

// 素材列表：解析后显示推荐素材（带相关度），未解析时显示知识库全部文档（排除生成的 bid 文件）
const availableMaterials = computed(() => {
  const excludeId = bidDocId.value
  const recMap = {}
  for (const m of parseResult.value?.recommended_materials || []) {
    recMap[m.id] = m
  }
  const hasRecommended = Object.keys(recMap).length > 0
  const seen = new Set()
  const result = []
  for (const doc of kbStore.documents) {
    if (doc.id === excludeId) continue
    if (doc.filename.startsWith('bid_')) continue  // 排除生成的投标文件
    if (seen.has(doc.filename)) continue  // 按文件名去重
    seen.add(doc.filename)
    if (hasRecommended && !recMap[doc.id]) continue
    result.push(recMap[doc.id]
      ? { ...recMap[doc.id], file_type: doc.file_type, chunk_count: doc.chunk_count }
      : { id: doc.id, filename: doc.filename, file_type: doc.file_type, chunk_count: doc.chunk_count })
  }
  return result
})

function scoreClass(score) {
  if (score == null) return ''
  const s = 1 - Math.abs(score)
  if (s > 0.85) return 'score-high'
  if (s > 0.7) return 'score-mid'
  return 'score-low'
}

// 匹配度颜色（用于 match_score 显示）
function matchScoreClass(level) {
  if (level === 'high') return 'match-high'
  if (level === 'mid') return 'match-mid'
  return 'match-low'
}

// 从 matchCheckResult 中查找某素材的匹配信息
function getMatchInfo(docId) {
  if (!matchCheckResult.value) return null
  return matchCheckResult.value.materials.find(m => m.doc_id === docId) || null
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append("file", file)
  const uploadResp = await api.post("/api/kb/documents", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  })
  await kbStore.fetchDocuments()
  bidFile.value = file
  bidDocId.value = uploadResp.data.doc_id
  try {
    const resp = await api.post("/api/bid/parse", { file_path: uploadResp.data.file_path })
    parseResult.value = resp.data
    const recommended = resp.data.recommended_materials || []
    selectedMaterials.value = recommended.map(m => m.id)
    ElMessage.success("招标文件解析完成" + (recommended.length ? `，已自动关联 ${recommended.length} 个相关素材` : ""))
  } catch {
    ElMessage.error("解析失败")
  }
}

function toggleMaterial(id) {
  const idx = selectedMaterials.value.indexOf(id)
  if (idx >= 0) selectedMaterials.value.splice(idx, 1)
  else selectedMaterials.value.push(id)
}

function triggerInlineUpload() {
  inlineUploadRef.value?.click()
}

async function handleInlineFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploadingInline.value = true
  try {
    const formData = new FormData()
    formData.append("file", file)
    const resp = await api.post("/api/kb/documents", formData, {
      headers: { "Content-Type": "multipart/form-data" }
    })
    await kbStore.fetchDocuments()
    // 自动选中新上传的文档
    const newDocId = resp.data.doc_id
    if (!selectedMaterials.value.includes(newDocId)) {
      selectedMaterials.value.push(newDocId)
    }
    ElMessage.success(`已上传并选中：${file.name}`)
    showUploadInline.value = false
  } catch {
    ElMessage.error("上传失败")
  } finally {
    uploadingInline.value = false
    e.target.value = ''  // 清空，允许重复上传同名文件
  }
}

// 匹配度检测
async function checkMatch() {
  if (!parseResult.value || !selectedMaterials.value.length) return
  checkingMatch.value = true
  matchCheckResult.value = null
  try {
    const resp = await api.post("/api/bid/match_check", {
      parse_result: parseResult.value,
      materials: selectedMaterials.value
    })
    matchCheckResult.value = resp.data
    if (resp.data.warning) {
      ElMessage.warning(resp.data.warning)
    } else {
      ElMessage.success("素材匹配度良好")
    }
  } catch {
    ElMessage.error("匹配度检测失败")
  } finally {
    checkingMatch.value = false
  }
}

async function handleGenerate() {
  generating.value = true
  reviewResult.value = null
  generatedFile.value = null
  progress.value = 0
  progressMessage.value = ""
  streamingContent.value = ""

  try {
    const token = localStorage.getItem("token") || ""
    const response = await fetch(`${import.meta.env.VITE_API_URL}/api/bid/generate/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        parse_result: parseResult.value,
        materials: selectedMaterials.value
      })
    })
    if (!response.ok) {
      const err = await response.json().catch(() => ({}))
      throw new Error(err.detail || `请求失败 ${response.status}`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split("\n")
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          const data = JSON.parse(raw)
          if (data.progress !== undefined) progress.value = data.progress
          if (data.message) progressMessage.value = data.message
          if (data.delta) streamingContent.value += data.delta
          if (data.stage === "done") {
            generatedFile.value = {
              name: data.filename,
              url: `${import.meta.env.VITE_API_URL}/api/bid/download/${data.filename}`,
            }
            reviewResult.value = data.review || null
          }
        } catch {}
      }
    }
    if (generatedFile.value) ElMessage.success("标书生成成功")
    else ElMessage.error("生成失败")
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "生成失败")
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.bid-page {
  padding-bottom: 64px;
}

/* ── Page Header ── */
.page-header {
  margin-bottom: 32px;
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
}

/* ── Grid ── */
.bid-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  align-items: start;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--color-ink-subtle);
  padding: 0 2px;
}

/* ── Upload Zone ── */
.upload-zone {
  background: var(--color-surface-1);
  border: 1px dashed var(--color-hairline-strong);
  border-radius: var(--radius-lg);
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.upload-zone:hover {
  border-color: var(--color-primary);
  background: rgba(94, 105, 209, 0.04);
}
.upload-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--color-ink-subtle);
  margin-bottom: 4px;
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

/* ── File Card ── */
.file-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 16px;
}
.file-card-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}
.file-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--color-ink-subtle);
  flex-shrink: 0;
}
.file-meta {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.file-status {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-top: 2px;
}
.file-status.uploading {
  color: var(--color-primary);
}

/* ── Parsed Section ── */
.parsed-section {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.health-strip {
  display: flex;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-hairline);
  flex-wrap: wrap;
}
.health-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--color-ink-subtle);
}
.health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-hairline-strong);
}
.health-item.pass .health-dot { background: var(--color-semantic-success); }
.health-item.warning .health-dot { background: var(--color-semantic-warning); }
.health-item.fail .health-dot { background: var(--color-semantic-error); }

.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-ink-tertiary);
}
.field-value {
  font-size: 14px;
  color: var(--color-ink);
}
.field-value.large {
  font-size: 17px;
  font-weight: 500;
  letter-spacing: -0.2px;
}
.field-input {
  --el-input-bg-color: var(--color-surface-2);
  --el-input-border-color: var(--color-hairline-strong);
  --el-input-text-color: var(--color-ink);
  --el-input-placeholder-color: var(--color-ink-tertiary);
  max-width: 400px;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.tag-add-input {
  width: 100px;
}

.raw-toggle {
  border-top: 1px solid var(--color-hairline);
  padding-top: 12px;
}
.raw-toggle-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--color-ink-subtle);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  font-family: inherit;
}
.raw-toggle-btn:hover {
  color: var(--color-ink);
}
.toggle-arrow {
  transition: transform 0.2s;
  font-size: 12px;
}
.toggle-arrow.open {
  transform: rotate(90deg);
}
.raw-content {
  margin-top: 10px;
  font-size: 12px;
  color: var(--color-ink-tertiary);
  line-height: 1.6;
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
  background: var(--color-surface-2);
  border-radius: var(--radius-md);
  padding: 12px;
}

/* ── Materials Card ── */
.materials-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 16px;
  min-height: 120px;
}
.material-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 6px;
}
.material-item:hover {
  border-color: var(--color-primary);
  background: var(--color-surface-1);
}
.material-item.selected {
  border-color: var(--color-primary);
  background: color-mix(in srgb, var(--color-primary) 6%, transparent);
}
.material-info {
  flex: 1;
  min-width: 0;
}
.material-name {
  font-size: 13px;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 3px;
}
.material-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.meta-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--color-hairline);
  color: var(--color-ink-muted);
  letter-spacing: 0.3px;
}
.meta-chunks {
  font-size: 11px;
  color: var(--color-ink-tertiary);
}
.meta-score {
  font-size: 11px;
  font-weight: 500;
}
.meta-score.score-high { color: #22c55e; }
.meta-score.score-mid { color: #f59e0b; }
.meta-score.score-low { color: var(--color-ink-tertiary); }

.empty-materials {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 24px 0;
  text-align: center;
}
.empty-icon {
  font-size: 28px;
  opacity: 0.4;
}
.empty-text {
  font-size: 13px;
  color: var(--color-ink-subtle);
}
.empty-hint {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  max-width: 260px;
}

/* ── Materials Footer ── */
.materials-footer {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--color-hairline);
}

/* ── Inline Upload ── */
.inline-upload-area {
  margin-top: 10px;
  padding: 12px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
}

/* ── Match Summary ── */
.match-summary {
  margin-top: 12px;
  padding: 12px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
}
.match-summary.has-warning {
  border-color: var(--color-semantic-warning);
  background: rgba(230, 162, 60, 0.05);
}
.match-summary-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.match-avg {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-primary);
}
.match-bars {
  display: flex;
  gap: 12px;
}
.bar-label {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-pill, 9999px);
}
.bar-label.high { background: rgba(34, 197, 94, 0.1); color: #22c55e; }
.bar-label.mid { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
.bar-label.low { background: rgba(245, 108, 108, 0.1); color: #f56c6c; }
.match-warning {
  margin-top: 8px;
  font-size: 11px;
  color: var(--color-semantic-warning);
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── Match Low Border ── */
.material-item.match-low {
  border-color: rgba(245, 108, 108, 0.4) !important;
}

/* ── Generate Card ── */
.generate-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.generate-btn {
  width: 100%;
  height: 42px;
  font-size: 14px !important;
  font-weight: 500 !important;
}

/* ── Generating Panel ── */
.generating-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gen-progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gen-stage {
  font-size: 12px;
  color: var(--color-ink-subtle);
}
.gen-pct {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
}
.gen-progress-bar {
  height: 4px;
  background: var(--color-surface-2);
  border-radius: 2px;
  overflow: hidden;
}
.gen-progress-fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.streaming-preview {
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.streaming-header {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--color-ink-tertiary);
  padding: 6px 12px;
  border-bottom: 1px solid var(--color-hairline);
  background: var(--color-surface-3);
}
.streaming-text {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-ink-muted);
  padding: 12px;
  max-height: 260px;
  overflow-y: auto;
  white-space: pre-wrap;
  line-height: 1.6;
}

/* ── Done Panel ── */
.done-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.done-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-semantic-success);
}
.download-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline-strong);
  border-radius: var(--radius-md);
  padding: 8px 14px;
  text-decoration: none;
  transition: all 0.15s;
}
.download-btn:hover {
  background: var(--color-surface-3);
  border-color: var(--color-hairline-tertiary);
  color: var(--color-ink);
}

/* ── Review Panel ── */
.review-panel {
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  padding: 14px;
}
.review-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.review-score {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-ink);
  letter-spacing: -0.4px;
}
.review-status {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-pill, 9999px);
}
.review-status.pass {
  background: rgba(39, 166, 68, 0.1);
  color: var(--color-semantic-success);
}
.review-status.fail {
  background: rgba(245, 108, 108, 0.1);
  color: var(--color-semantic-error);
}
.review-issues {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: var(--color-ink-subtle);
  line-height: 1.8;
}

/* ── Shared ── */
.clickable-underline {
  cursor: pointer;
  text-decoration: underline dashed var(--color-primary);
  text-underline-offset: 3px;
}
.clickable-underline:hover {
  color: var(--color-primary-hover);
}
</style>
