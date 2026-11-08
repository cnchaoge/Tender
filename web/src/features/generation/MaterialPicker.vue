<template>
<!-- 素材选择 -->
    <div class="section-label">素材选择</div>
    <div class="materials-card">
      <div v-if="availableMaterials.length" class="material-list">
        <div
          v-for="mat in availableMaterials"
          :key="mat.id"
          class="material-item"
          :class="{ selected: selectedMaterials.includes(mat.id), 'match-low': getMatchInfo(mat.id)?.level === 'low' }"
          @click="emit('toggle', mat.id)"
        >
          <el-checkbox :value="mat.id" :model-value="selectedMaterials.includes(mat.id)" />
          <div class="material-info">
            <div class="material-name">
              {{ mat.filename }}
              <el-button
                v-if="mat.relevance_score != null"
                text
                size="small"
                class="preview-btn"
                @click.stop="openPreview(mat)"
              >
                预览
              </el-button>
            </div>
            <div class="material-meta">
              <span class="meta-badge">{{ mat.file_type?.toUpperCase() }}</span>
              <span v-if="mat.chunk_count" class="meta-chunks">{{ mat.chunk_count }} 个切片</span>
              <!-- 匹配度分数（match_check 返回） -->
              <span v-if="getMatchInfo(mat.id)" class="meta-score" :class="matchScoreClass(getMatchInfo(mat.id).level)">
                匹配度 {{ getMatchInfo(mat.id).score }}%
              </span>
              <!-- RAG 推荐相关度 + 匹配理由 -->
              <span v-else-if="mat.relevance_score != null" class="meta-score" :class="scoreClass(mat.relevance_score)">
                匹配度 {{ Math.round(mat.relevance_score * 100) }}%
              </span>
              <span v-if="mat.relevance_reason" class="meta-reason">{{ mat.relevance_reason }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="empty-materials" v-else>
        <div class="empty-icon">📂</div>
        <div class="empty-text">知识库暂无文档</div>
        <div class="empty-hint">上传施工方案、标准合同等素材，系统将自动关联</div>
      </div>

      <!-- 内联上传区 -->
      <div class="inline-upload-area" v-if="showUploadInline">
        <el-upload
          ref="inlineUploadRef"
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onInlineChange"
          accept=".pdf,.docx,.xlsx,.xls,.pptx,.md,.txt,.jpg,.jpeg,.png"
        >
          <el-button type="default" size="small" :loading="uploadingInline">
            <el-icon><component :is="Upload" /></el-icon>
            {{ uploadingInline ? '上传中...' : '确认上传' }}
          </el-button>
        </el-upload>
        <el-button size="small" @click="emit('update:showUploadInline', false)" style="margin-left: 8px">取消</el-button>
      </div>

      <!-- 素材操作栏 -->
      <div class="materials-footer">
        <el-button size="small" type="default" @click="emit('update:showUploadInline', !showUploadInline)">
          <el-icon><component :is="Plus" /></el-icon>
          {{ showUploadInline ? '取消' : '新增素材' }}
        </el-button>
        <el-button
          v-if="selectedMaterials.length && parseResult"
          size="small"
          type="default"
          :loading="checkingMatch"
          @click="emit('check-match')"
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

<!-- 素材章节预览 -->
<el-dialog v-model="previewDialogVisible" title="相似章节" width="600px" class="bid-page">
  <div v-if="previewLoading" style="text-align:center;padding:40px">
    <el-icon class="is-loading" size="20"><Loading /></el-icon>
  </div>
  <template v-else>
    <div class="preview-header" v-if="previewData">
      <span class="preview-filename">{{ previewData.filename }}</span>
      <span class="preview-count" v-if="previewData.ranked">按相关度排序 · {{ previewData.section_count }} 个相似片段</span>
      <span class="preview-count" v-else>共 {{ previewData.section_count }} 个章节/片段</span>
    </div>
    <div v-if="previewData?.sections?.length" class="preview-sections">
      <div v-for="sec in previewData.sections" :key="sec.rank ?? sec.index" class="preview-section">
        <div class="preview-section-header">
          <span class="preview-section-num">相似 #{{ (sec.rank ?? sec.index) + 1 }}</span>
          <span v-if="sec.section_name" class="preview-section-name">{{ sec.section_name }}</span>
          <span v-if="sec.section_type" class="preview-section-type">{{ sec.section_type }}</span>
          <span v-if="relevanceLabel(sec.score)" class="preview-section-type">{{ relevanceLabel(sec.score) }}</span>
        </div>
        <div class="preview-section-text">{{ sec.text }}</div>
        <div class="preview-section-actions">
          <el-button size="small" text @click="copySection(sec)">
            引用此段
          </el-button>
        </div>
      </div>
    </div>
    <el-empty v-else-if="!previewLoading" :image-size="60" :description="previewData?.message || '未找到与当前招标文件相似的章节'" />
  </template>
</el-dialog>
</template>

<script setup>
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { ArrowRight, Files, Loading, Plus, Upload } from "@element-plus/icons-vue"
import { bid } from "../../api"

const props = defineProps({
  availableMaterials: { type: Array, default: () => [] },
  selectedMaterials: { type: Array, default: () => [] },
  parseResult: { type: Object, default: null },
  matchCheckResult: { type: Object, default: null },
  checkingMatch: { type: Boolean, default: false },
  showUploadInline: { type: Boolean, default: false },
  uploadingInline: { type: Boolean, default: false },
})
const emit = defineEmits(["toggle", "update:showUploadInline", "check-match", "inline-change"])

const inlineUploadRef = ref(null)
const previewDialogVisible = ref(false)
const previewData = ref(null)
const previewLoading = ref(false)

function onInlineChange(uploadFile) {
  emit("inline-change", uploadFile)
}

function scoreClass(score) {
  if (score == null) return ""
  const s = 1 - Math.abs(score)
  if (s > 0.85) return "score-high"
  if (s > 0.7) return "score-mid"
  return "score-low"
}

function relevanceLabel(score) {
  const n = Number(score)
  if (!Number.isFinite(n) || n <= 0) return ""
  return `相关度 ${Math.round(Math.min(1, n) * 100)}%`
}

function previewContext() {
  const parsed = props.parseResult
  if (!parsed) return {}
  return {
    parse_result: {
      project_name: parsed.project_name || "",
      deadline: parsed.deadline || "",
      requirements: parsed.requirements || [],
      qualification: parsed.qualification || [],
      scoring: parsed.scoring || {},
      technical_requirements: parsed.technical_requirements || parsed.tech_requirements || [],
    },
  }
}

function matchScoreClass(level) {
  if (level === "high") return "match-high"
  if (level === "mid") return "match-mid"
  return "match-low"
}

function getMatchInfo(docId) {
  if (!props.matchCheckResult) return null
  return props.matchCheckResult.materials.find(m => m.doc_id === docId) || null
}

function copySection(sec) {
  const text = sec.section_name ? `【${sec.section_name}】\n${sec.text}` : sec.text
  navigator.clipboard.writeText(text).then(() => {
    ElMessage.success("已复制到剪贴板，可在生成前粘贴到提示词中")
  }).catch(() => {
    ElMessage.warning("复制失败，请手动选择文本")
  })
}

async function openPreview(mat) {
  if (mat.relevance_score == null && !mat.matched_excerpts) return
  previewLoading.value = true
  previewDialogVisible.value = true
  previewData.value = null
  try {
    const resp = await bid.recommendPreview(mat.id, previewContext())
    previewData.value = resp.data
  } catch (e) {
    const detail = e?.response?.data?.detail
    previewData.value = {
      filename: mat.filename,
      sections: [],
      section_count: 0,
      ranked: false,
      message: typeof detail === "string" ? detail : "相似章节加载失败",
    }
  } finally {
    previewLoading.value = false
  }
}
</script>

