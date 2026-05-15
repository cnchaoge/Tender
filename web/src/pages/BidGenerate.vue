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

          <!-- Scoring Standards -->
          <div class="field-group" v-if="parseResult.scoring && parseResult.scoring.sections?.length">
            <div class="field-label">评分标准</div>
            <div class="scoring-summary">
              <span class="scoring-method">{{ parseResult.scoring.method || '综合评分法' }}</span>
              <span class="scoring-total">总分 {{ parseResult.scoring.total_score || 100 }}</span>
            </div>
            <div class="scoring-sections">
              <div
                v-for="(section, si) in parseResult.scoring.sections"
                :key="si"
                class="scoring-section"
              >
                <div class="scoring-section-header" @click="toggleScoringSection(si)">
                  <span class="scoring-section-name">{{ section.name }}</span>
                  <span class="scoring-section-weight">{{ section.weight }}%</span>
                  <el-icon class="scoring-arrow" :class="{ open: openScoringSections.has(si) }"><component :is="ArrowRight" /></el-icon>
                </div>
                <div v-if="openScoringSections.has(si)" class="scoring-items">
                  <div
                    v-for="(item, ii) in section.items"
                    :key="ii"
                    class="scoring-item"
                    :class="{ 'disqualify-item': item.disqualify_if_fail }"
                  >
                    <div class="scoring-item-row">
                      <span class="scoring-item-name">{{ item.name }}</span>
                      <span class="scoring-item-score">{{ item.score }}/{{ item.max_score || item.score }}分</span>
                    </div>
                    <div class="scoring-item-meta">
                      <span class="scoring-item-type">{{ scoringTypeLabel(item.type) }}</span>
                      <span v-if="item.disqualify_if_fail" class="scoring-disqualify-tag">不满足则废标</span>
                      <span v-if="item.formula" class="scoring-formula">{{ item.formula }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="!parseResult.scoring.sections?.length" class="scoring-empty">
              未识别到评分标准，请手动补充
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
              accept=".pdf,.docx,.xlsx,.xls,.pptx,.md,.txt,.jpg,.jpeg,.png"
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
          <!-- 策略选择 -->
          <div class="strategy-selector">
            <div class="strategy-label">策略选择</div>
            <div class="strategy-options">
              <label
                v-for="opt in strategyOptions"
                :key="opt.value"
                class="strategy-option"
                :class="{ active: selectedStrategy === opt.value }"
              >
                <input type="radio" :value="opt.value" v-model="selectedStrategy" style="display:none" />
                <div class="strategy-option-inner">
                  <span class="strategy-name">{{ opt.label }}</span>
                  <span class="strategy-desc">{{ opt.desc }}</span>
                </div>
              </label>
            </div>
          </div>

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
            <!-- Chapter progress bars -->
            <div class="chapter-progress-list" v-if="Object.keys(chapterStates).length">
              <div
                v-for="(state, chIdx) in chapterStates"
                :key="chIdx"
                class="chapter-progress-item"
              >
                <div class="chapter-name">{{ state.name }}</div>
                <div class="chapter-bar-wrap">
                  <el-progress
                    :percentage="state.progress"
                    :status="state.status === 'completed' ? 'success' : undefined"
                    :stroke-width="8"
                    :show-text="true"
                    :format="p => p + '%'"
                  />
                </div>
              </div>
            </div>
            <!-- Streaming Preview (Markdown rendered) -->
            <div class="streaming-preview" v-if="renderedContent">
              <div class="streaming-header">实时输出</div>
              <div class="streaming-html" v-html="renderedContent"></div>
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

          <!-- Done: 格式检查结果 -->
          <div v-if="formatResult && !generating" class="format-panel" :class="{ 'has-warnings': !formatResult.passed }">
            <div class="format-header">
              <span class="format-icon">📋</span>
              <span class="format-title">格式检查</span>
              <span class="format-score" :class="formatResult.score >= 80 ? 'pass' : formatResult.score >= 60 ? 'mid' : 'fail'">
                {{ formatResult.score }}分
              </span>
            </div>
            <ul class="format-warnings">
              <li
                v-for="(w, wi) in formatResult.warnings"
                :key="wi"
                class="format-item"
                :class="w.status"
              >
                <span class="format-item-icon">{{ w.status === 'pass' ? '✅' : '⚠️' }}</span>
                <span class="format-item-name">{{ w.item }}</span>
                <span class="format-item-detail">{{ w.detail }}</span>
              </li>
            </ul>
          </div>

          <!-- Done: 废标项检测结果 -->
          <div v-if="violationResult && !generating && !violationResult.passed" class="violation-panel fail">
            <div class="violation-header">
              <span class="violation-icon">🚨</span>
              <span class="violation-title">废标风险检测</span>
              <span class="violation-badge">存在风险</span>
            </div>
            <div class="violation-summary">
              共 {{ violationResult.summary?.total_violations || 0 }} 项，
              <span class="disqualify" v-if="violationResult.summary?.disqualify_count > 0">
                含 {{ violationResult.summary.disqualify_count }} 项必废标项
              </span>
              <span class="high-risk" v-else>
                含 {{ violationResult.summary?.high_risk_count || 0 }} 项高风险项
              </span>
            </div>
            <ul class="violation-list">
              <li v-for="(v, i) in violationResult.violations" :key="i" class="violation-item" :class="{ disqualify: v.is_disqualify }">
                <div class="violation-name">{{ v.rule_name }}</div>
                <div class="violation-fix">{{ v.fix_suggestion }}</div>
              </li>
            </ul>
          </div>

          <!-- Done: 标书查重结果 -->
          <div v-if="plagiarismResult && !generating" class="plagiarism-panel" :class="{ 'has-risk': !plagiarismResult.passed }">
            <div class="plagiarism-header">
              <span class="plagiarism-icon">🔍</span>
              <span class="plagiarism-title">标书查重</span>
              <span class="plagiarism-score" :class="plagiarismResult.overall_score > 60 ? 'high' : plagiarismResult.overall_score > 30 ? 'mid' : 'low'">
                {{ plagiarismResult.overall_score }}% 相似度
              </span>
            </div>
            <div class="plagiarism-summary" v-if="plagiarismResult.high_risk_sections > 0">
              发现 {{ plagiarismResult.high_risk_sections }} 个高重复章节，建议人工确认
            </div>
            <div class="plagiarism-sections" v-if="plagiarismResult.sections?.length">
              <div
                v-for="sec in plagiarismResult.sections.filter(s => s.risk_level !== 'low')"
                :key="sec.section_index"
                class="plagiarism-sec-item"
                :class="sec.risk_level"
              >
                <span class="sec-name">{{ sec.section_name }}</span>
                <span class="sec-score">{{ sec.similarity_score }}%</span>
                <span v-if="sec.matched_bids?.length" class="sec-source">
                  相似于：{{ sec.matched_bids[0].filename }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 历史版本 -->
        <div class="section-label" style="margin-top: 28px">历史版本</div>
        <div class="versions-card">
          <div v-if="loadingVersions" class="versions-loading">
            <span class="versions-spinner"></span> 加载中...</div>
          <div v-else-if="versionList.length === 0" class="versions-empty">
            暂无历史版本
          </div>
          <div v-else class="version-list">
            <div
              v-for="v in versionList"
              :key="v.id"
              class="version-item"
              :class="{ expanded: expandedVersionId === v.id }"
            >
              <div class="version-header" @click="toggleVersion(v.id)">
                <div class="version-info">
                  <span class="version-date">{{ formatDate(v.generated_at) }}</span>
                  <span class="version-name">{{ v.project_name || '未命名项目' }}</span>
                </div>
                <el-icon class="version-arrow" :class="{ open: expandedVersionId === v.id }"><component :is="ArrowRight" /></el-icon>
              </div>
              <div v-if="expandedVersionId === v.id" class="version-body">
                <div class="version-content" v-html="renderMarkdown(versionContents[v.id] || '')"></div>
                <div class="version-actions">
                  <el-button size="small" @click="regenerateFromVersion(v.id)">
                    基于此版本重新生成
                  </el-button>
                  <el-button size="small" @click="showCompareDialog(v.id)">
                    对比
                  </el-button>
                  <a v-if="v.file_path" :href="`${apiBase()}/api/bid/download/${getFilename(v.file_path)}`" target="_blank" class="version-download">
                    <el-icon><component :is="Download" /></el-icon>
                    下载
                  </a>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 对比弹窗 -->
        <el-dialog v-model="compareDialogVisible" title="版本对比" width="800px" :close-on-click-modal="true">
          <div class="compare-controls">
            <el-select v-model="compareFromId" placeholder="选择版本A" size="small" style="width: 200px">
              <el-option v-for="v in versionList" :key="v.id" :label="`v${v.id} - ${v.project_name || '未命名'}`" :value="v.id" />
            </el-select>
            <span style="padding: 0 8px; color: var(--color-ink-subtle)">vs</span>
            <el-select v-model="compareToId" placeholder="选择版本B" size="small" style="width: 200px">
              <el-option v-for="v in versionList" :key="v.id" :label="`v${v.id} - ${v.project_name || '未命名'}`" :value="v.id" />
            </el-select>
            <el-button size="small" type="primary" :loading="comparing" @click="doCompare" style="margin-left: 8px">对比</el-button>
          </div>
          <pre v-if="compareDiff" class="compare-diff">{{ compareDiff }}</pre>
          <div v-else class="compare-empty">选择两个版本后点击对比</div>
        </el-dialog>
      </div>
    </div>

    <!-- 规划阶段弹窗 -->
    <el-dialog
      v-model="planDialogVisible"
      title="确认标书结构"
      width="560px"
      :close-on-click-modal="false"
      class="plan-dialog"
    >
      <div class="plan-intro">请确认以下章节结构，生成过程中将按此结构编写各章节内容：</div>
      <div class="plan-chapters">
        <div
          v-for="(ch, idx) in planningChapters"
          :key="idx"
          class="plan-chapter-item"
        >
          <div class="plan-chapter-num">{{ idx + 1 }}</div>
          <div class="plan-chapter-body">
            <div class="plan-chapter-name">{{ ch.name }}</div>
            <div class="plan-chapter-desc">{{ ch.description }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="planDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmPlanAndGenerate">确认并生成正文</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { Upload, Document, Files, Check, Download, ArrowRight, Plus } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"
import api from "../api"
import { marked } from "marked"
// Configure marked for security (no async)
// Configure marked for security (no async)
marked.setOptions({ breaks: true, gfm: true })

onMounted(() => {
  loadVersions()
})

const kbStore = useKbStore()
// 统一 API 基础路径：dev 走相对路径（Vite proxy），prod 用完整 URL
function apiBase() {
  return import.meta.env.DEV ? "" : (import.meta.env.VITE_API_URL || "http://localhost:8000")
}
const bidFile = ref(null)
const bidDocId = ref(null)  // 上传的招标文件 doc_id，不参与素材选择
const parseResult = ref(null)
const selectedMaterials = ref([])
const generating = ref(false)
const generatedFile = ref(null)
const reviewResult = ref(null)
const progress = ref(0)
const progressMessage = ref("")
const streamingContent = ref("")   // 原始 markdown 文本
const renderedContent = ref("")    // 渲染后的 HTML
const editingProjectName = ref(false)
const editingDeadline = ref(false)
const showRawText = ref(false)
const fileInputRef = ref(null)
const showUploadInline = ref(false)  // 内联上传区展开
const uploadingInline = ref(false)
const inlineUploadRef = ref(null)
const matchCheckResult = ref(null)  // 匹配度检测结果
const checkingMatch = ref(false)
const planningChapters = ref([])    // 规划阶段章节列表
const planDialogVisible = ref(false) // 规划阶段弹窗
const violationResult = ref(null)   // 废标项检测结果
const plagiarismResult = ref(null)   // 标书查重结果
const formatResult = ref(null)       // 格式检查结果
const openScoringSections = ref(new Set()) // 展开的评分项section索引

// 投标策略选项
const strategyOptions = [
  { label: "技术优先型", value: "技术优先型", desc: "技术方案详细、质量最高、价格适中" },
  { label: "成本控制型", value: "成本控制型", desc: "价格最低方案，利润优先" },
  { label: "综合均衡型", value: "综合均衡型", desc: "技术和价格平衡，性价比最优" },
]
const selectedStrategy = ref("综合均衡型") // 默认选中

// Chapter progress state: Map<chapter_index, {name, status, progress}>
const chapterStates = ref({})

// 历史版本
const versionList = ref([])
const loadingVersions = ref(false)
const expandedVersionId = ref(null)
const versionContents = ref({})
const compareDialogVisible = ref(false)
const compareFromId = ref(null)
const compareToId = ref(null)
const compareDiff = ref("")
const comparing = ref(false)

function toggleScoringSection(idx) {
  if (openScoringSections.value.has(idx)) openScoringSections.value.delete(idx)
  else openScoringSections.value.add(idx)
}

function scoringTypeLabel(type) {
  const map = { expert: '专家打分', formula: '公式计算', qualified: '满足即得分' }
  return map[type] || type || '未知'
}

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

// 历史版本
async function loadVersions() {
  loadingVersions.value = true
  try {
    const resp = await api.get("/api/bid/versions", {
      params: parseResult.value?.project_name
        ? { project_name: parseResult.value.project_name }
        : {}
    })
    versionList.value = resp.data.versions || []
  } catch {
    // 静默失败
  } finally {
    loadingVersions.value = false
  }
}

function toggleVersion(vid) {
  if (expandedVersionId.value === vid) {
    expandedVersionId.value = null
    return
  }
  expandedVersionId.value = vid
  if (!versionContents.value[vid]) {
    loadVersionContent(vid)
  }
}

async function loadVersionContent(vid) {
  try {
    const resp = await api.get(`/api/bid/versions/${vid}`)
    versionContents.value[vid] = resp.data.bid_content || ""
  } catch {
    versionContents.value[vid] = "加载失败"
  }
}

async function regenerateFromVersion(vid) {
  try {
    const resp = await api.post(`/api/bid/versions/${vid}/restore`)
    const data = resp.data
    if (data.parse_result) {
      parseResult.value = data.parse_result
    }
    if (data.material_ids?.length) {
      selectedMaterials.value = data.material_ids
    }
    ElMessage.success("已加载版本数据，点击生成按钮重新生成")
  } catch {
    ElMessage.error("恢复版本失败")
  }
}

async function showCompareDialog(vid) {
  compareFromId.value = vid
  compareToId.value = versionList.value.find(v => v.id !== vid)?.id || null
  compareDiff.value = ""
  compareDialogVisible.value = true
}

async function doCompare() {
  if (!compareFromId.value || !compareToId.value) return
  comparing.value = true
  try {
    const resp = await api.get("/api/bid/versions/compare", {
      params: { from_id: compareFromId.value, to_id: compareToId.value }
    })
    compareDiff.value = resp.data.diff_text || "无差异"
  } catch {
    ElMessage.error("对比失败")
  } finally {
    comparing.value = false
  }
}

function formatDate(ts) {
  if (!ts) return ""
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`
}

function getFilename(path) {
  return path ? path.split("/").pop() : ""
}

function renderMarkdown(text) {
  return marked.parse(text || "")
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
  // 阶段1：先调 plan API 获取章节大纲
  planningChapters.value = []
  planDialogVisible.value = false
  try {
    const resp = await api.post("/api/bid/plan", {
      parse_result: parseResult.value,
      materials: selectedMaterials.value
    })
    planningChapters.value = resp.data.chapters || []
  } catch {
    ElMessage.error("规划章节失败，请重试")
    return
  }
  // 弹出确认框，用户确认后再生成
  planDialogVisible.value = true
}

async function confirmPlanAndGenerate() {
  planDialogVisible.value = false
  // P0-2: 前置废标检查（基于招标文件 parse_result）
  violationResult.value = null
  generating.value = true
  progress.value = 5
  progressMessage.value = "招标文件合规性检测..."
  try {
    const vResp = await api.post("/api/bid/violation_check", {
      parse_result: parseResult.value,
      raw_text: parseResult.value.raw_text || "",
    })
    const vResult = vResp.data
    progress.value = 10
    progressMessage.value = ""
    if (!vResult.passed && vResult.summary?.disqualify_count > 0) {
      // 有必废标项，弹警告让用户确认
      generating.value = false
      violationResult.value = vResult
      const confirmed = await ElMessageBox.confirm(
        `检测到 ${vResult.summary.disqualify_count} 项必废标风险，是否仍要强制生成？（生成后标书将存在废标风险）`,
        "招标文件合规性警告",
        { confirmButtonText: "强制生成", cancelButtonText: "取消", type: "warning" }
      ).catch(() => false)
      if (!confirmed) return
      generating.value = true
      progress.value = 10
      progressMessage.value = "已确认，继续生成..."
    } else if (!vResult.passed && vResult.summary?.high_risk_count > 0) {
      // 有高风险项，提示但允许继续
      violationResult.value = vResult
      ElMessage.warning(`检测到 ${vResult.summary.high_risk_count} 项高风险项，请留意`)
    } else if (vResult.passed) {
      violationResult.value = { passed: true }
    }
  } catch {
    // 检查失败不阻断生成
  }
  generating.value = false
  await doGenerate()
}

async function doGenerate() {
  generating.value = true
  reviewResult.value = null
  generatedFile.value = null
  progress.value = 0
  progressMessage.value = ""
  streamingContent.value = ""
  renderedContent.value = ""
  chapterStates.value = {}

  // Initialize chapter states from planningChapters
  for (const ch of planningChapters.value) {
    chapterStates.value[ch.index] = {
      name: ch.name,
      status: "pending",
      progress: 0,
    }
  }

  try {
    const token = localStorage.getItem("token") || ""
    const response = await fetch(`${apiBase()}/api/bid/generate/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        parse_result: parseResult.value,
        materials: selectedMaterials.value,
        chapters: planningChapters.value,
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
          if (data.delta) {
            streamingContent.value += data.delta
            renderedContent.value = marked.parse(streamingContent.value)
          }
          if (data.stage === "violation_fail") {
            // 严重废标风险，中断生成
            violationResult.value = data.violation_result
            generating.value = false
            ElMessage.error("检测到废标风险，生成已中止！请检查标书内容后重试")
            return
          }
          if (data.stage === "violation_warn") {
            violationResult.value = data.violation_result
          }
          if (data.stage === "done") {
            generatedFile.value = {
              name: data.filename,
              url: `${apiBase()}/api/bid/download/${data.filename}`,
            }
            reviewResult.value = data.review || null
            if (data.violation_result) violationResult.value = data.violation_result
            if (data.plagiarism_result) plagiarismResult.value = data.plagiarism_result
            if (data.format_result) formatResult.value = data.format_result
            // 刷新历史版本列表
            loadVersions()
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

/* ── Scoring Section ── */
.scoring-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.scoring-method {
  font-size: 12px;
  background: var(--color-primary);
  color: #fff;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: 500;
}
.scoring-total {
  font-size: 12px;
  color: var(--color-ink-subtle);
}
.scoring-sections {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.scoring-section {
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.scoring-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-surface-2);
  cursor: pointer;
  user-select: none;
}
.scoring-section-header:hover { background: var(--color-surface-3); }
.scoring-section-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
}
.scoring-section-weight {
  font-size: 12px;
  color: var(--color-ink-subtle);
}
.scoring-arrow {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  transition: transform 0.2s;
}
.scoring-arrow.open { transform: rotate(90deg); }
.scoring-items {
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: #fff;
}
.scoring-item {
  padding: 7px 10px;
  border-radius: 5px;
  background: var(--color-surface-2);
}
.scoring-item.disqualify-item {
  background: rgba(245, 108, 108, 0.08);
  border-left: 3px solid var(--color-semantic-error);
}
.scoring-item-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.scoring-item-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-ink);
}
.scoring-item-score {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-primary);
}
.scoring-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.scoring-item-type {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--color-hairline);
  border-radius: 3px;
  color: var(--color-ink-muted);
}
.scoring-disqualify-tag {
  font-size: 10px;
  padding: 1px 5px;
  background: rgba(245, 108, 108, 0.12);
  color: var(--color-semantic-error);
  border-radius: 3px;
  font-weight: 500;
}
.scoring-formula {
  font-size: 10px;
  color: var(--color-ink-tertiary);
  font-family: var(--font-mono);
}
.scoring-empty {
  font-size: 12px;
  color: var(--color-semantic-warning);
  font-style: italic;
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

/* ── Format Panel ── */
.format-panel {
  border-radius: var(--radius-md);
  padding: 14px;
  margin-top: 8px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
}
.format-panel.has-warnings {
  background: rgba(230, 162, 60, 0.05);
  border-color: rgba(230, 162, 60, 0.25);
}
.format-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.format-icon { font-size: 14px; }
.format-title { font-size: 13px; font-weight: 600; color: var(--color-ink); flex: 1; }
.format-score { font-size: 12px; font-weight: 600; }
.format-score.pass { color: var(--color-semantic-success); }
.format-score.mid { color: var(--color-semantic-warning); }
.format-score.fail { color: var(--color-semantic-error); }
.format-warnings {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.format-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  padding: 6px 8px;
  border-radius: 4px;
}
.format-item.pass { background: rgba(39, 166, 68, 0.06); }
.format-item.warning { background: rgba(230, 162, 60, 0.08); }
.format-item-icon { font-size: 11px; flex-shrink: 0; margin-top: 1px; }
.format-item-name { font-weight: 500; color: var(--color-ink); flex-shrink: 0; }
.format-item-detail { color: var(--color-ink-subtle); }

/* ── Violation Panel ── */
.violation-panel {
  border-radius: var(--radius-md);
  padding: 14px;
  margin-top: 8px;
}
.violation-panel.fail {
  background: rgba(245, 108, 108, 0.08);
  border: 1px solid rgba(245, 108, 108, 0.25);
}
.violation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.violation-icon { font-size: 16px; }
.violation-title { font-size: 13px; font-weight: 600; color: var(--color-ink); }
.violation-badge {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: 3px;
  background: rgba(245, 108, 108, 0.12);
  color: var(--color-semantic-error);
}
.violation-summary {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-bottom: 8px;
}
.violation-summary .disqualify { color: var(--color-semantic-error); font-weight: 600; }
.violation-summary .high-risk { color: var(--color-semantic-warning); font-weight: 500; }
.violation-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.violation-item {
  background: rgba(255,255,255,0.6);
  border-radius: 6px;
  padding: 8px 10px;
}
.violation-item.disqualify {
  background: rgba(245, 108, 108, 0.12);
  border-left: 3px solid var(--color-semantic-error);
}
.violation-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 3px;
}
.violation-fix {
  font-size: 11px;
  color: var(--color-ink-tertiary);
}

/* ── Plagiarism Panel ── */
.plagiarism-panel {
  border-radius: var(--radius-md);
  padding: 14px;
  margin-top: 8px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
}
.plagiarism-panel.has-risk {
  background: rgba(245, 108, 108, 0.05);
  border-color: rgba(245, 108, 108, 0.2);
}
.plagiarism-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.plagiarism-icon { font-size: 14px; }
.plagiarism-title { font-size: 13px; font-weight: 600; color: var(--color-ink); }
.plagiarism-score { font-size: 12px; font-weight: 600; margin-left: auto; }
.plagiarism-score.high { color: var(--color-semantic-error); }
.plagiarism-score.mid { color: var(--color-semantic-warning); }
.plagiarism-score.low { color: var(--color-semantic-success); }
.plagiarism-summary {
  font-size: 12px;
  color: var(--color-ink-subtle);
  margin-bottom: 8px;
}
.plagiarism-sections {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plagiarism-sec-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 5px 8px;
  border-radius: 4px;
}
.plagiarism-sec-item.high { background: rgba(245, 108, 108, 0.1); }
.plagiarism-sec-item.mid { background: rgba(230, 162, 60, 0.1); }
.plagiarism-sec-item.low { background: rgba(39, 166, 68, 0.08); }
.plagiarism-sec-item .sec-name { color: var(--color-ink); flex: 1; }
.plagiarism-sec-item .sec-score { font-weight: 600; }
.plagiarism-sec-item.high .sec-score { color: var(--color-semantic-error); }
.plagiarism-sec-item.mid .sec-score { color: var(--color-semantic-warning); }
.plagiarism-sec-item .sec-source { font-size: 11px; color: var(--color-ink-tertiary); }

/* ── Markdown Rendered Preview ── */
.streaming-html {
  padding: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-ink);
  max-height: 400px;
  overflow-y: auto;
}
.streaming-html :deep(h1) { font-size: 16px; font-weight: 600; margin: 0 0 8px; color: var(--color-ink); }
.streaming-html :deep(h2) { font-size: 14px; font-weight: 600; margin: 12px 0 6px; color: var(--color-ink); }
.streaming-html :deep(h3) { font-size: 13px; font-weight: 600; margin: 10px 0 4px; }
.streaming-html :deep(p) { margin: 0 0 8px; }
.streaming-html :deep(ul), .streaming-html :deep(ol) { margin: 0 0 8px; padding-left: 20px; }
.streaming-html :deep(li) { margin-bottom: 3px; }
.streaming-html :deep(table) { border-collapse: collapse; width: 100%; margin-bottom: 8px; font-size: 12px; }
.streaming-html :deep(th), .streaming-html :deep(td) {
  border: 1px solid var(--color-hairline-strong);
  padding: 5px 8px;
  text-align: left;
}
.streaming-html :deep(th) { background: var(--color-surface-2); font-weight: 500; }
.streaming-html :deep(code) { background: var(--color-surface-2); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
.streaming-html :deep(pre) { background: var(--color-surface-2); padding: 10px; border-radius: var(--radius-md); overflow-x: auto; margin-bottom: 8px; }
.streaming-html :deep(pre code) { background: none; padding: 0; }
.streaming-html :deep(blockquote) { border-left: 3px solid var(--color-primary); margin: 0 0 8px; padding: 4px 10px; background: rgba(59, 130, 246, 0.05); color: var(--color-ink-subtle); }

/* ── Plan Dialog ── */
.plan-intro {
  font-size: 13px;
  color: var(--color-ink-subtle);
  margin-bottom: 16px;
  line-height: 1.5;
}
.plan-chapters {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow-y: auto;
}
.plan-chapter-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
}
.plan-chapter-num {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--color-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 1px;
}
.plan-chapter-body {
  flex: 1;
}
.plan-chapter-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  margin-bottom: 3px;
}
.plan-chapter-desc {
  font-size: 12px;
  color: var(--color-ink-subtle);
  line-height: 1.4;
}

/* ── Version History ── */
.versions-card {
  background: var(--color-surface-1);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-lg);
  padding: 16px;
  min-height: 80px;
}
.versions-loading, .versions-empty {
  font-size: 12px;
  color: var(--color-ink-subtle);
  text-align: center;
  padding: 16px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}
.versions-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-hairline);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.version-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.version-item {
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.version-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--color-surface-2);
  user-select: none;
}
.version-header:hover { background: var(--color-surface-3); }
.version-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.version-date {
  font-size: 11px;
  color: var(--color-ink-subtle);
  flex-shrink: 0;
}
.version-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.version-arrow {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  transition: transform 0.2s;
  flex-shrink: 0;
}
.version-arrow.open { transform: rotate(90deg); }
.version-body {
  padding: 12px;
  border-top: 1px solid var(--color-hairline);
  background: #fff;
}
.version-content {
  font-size: 12px;
  color: var(--color-ink-subtle);
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 10px;
  line-height: 1.6;
}
.version-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.version-download {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-ink-subtle);
  text-decoration: none;
  padding: 5px 10px;
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-sm);
}
.version-download:hover { color: var(--color-ink); background: var(--color-surface-2); }

/* ── Compare Dialog ── */
.compare-controls {
  display: flex;
  align-items: center;
  margin-bottom: 16px;
}
.compare-diff {
  background: var(--color-surface-2);
  border: 1px solid var(--color-hairline);
  border-radius: var(--radius-md);
  padding: 16px;
  font-size: 12px;
  line-height: 1.6;
  max-height: 500px;
  overflow-y: auto;
  white-space: pre-wrap;
  font-family: var(--font-mono);
}
.compare-empty {
  font-size: 13px;
  color: var(--color-ink-subtle);
  text-align: center;
  padding: 40px;
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
