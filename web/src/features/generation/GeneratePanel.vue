<template>
<!-- 生成标书 -->
<div class="section-label" style="margin-top: 28px">生成</div>
<div class="generate-card">
  <!-- 策略选择 -->
  <div class="strategy-selector">
    <div class="strategy-label">策略选择</div>
    <div class="strategy-tabs">
      <label
        v-for="opt in strategyOptions"
        :key="opt.value"
        class="strategy-tab"
        :class="{ active: selectedStrategy === opt.value }"
      >
        <input type="radio" :value="opt.value" :checked="selectedStrategy === opt.value" @change="emit('update:selectedStrategy', opt.value)" style="display:none" />
        <div class="strategy-tab-inner">
          <span class="strategy-icon">{{ opt.icon }}</span>
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
    @click="emit('generate')"
  >
    <el-icon v-if="!generating"><component :is="Files" /></el-icon>
    生成投标标书
  </el-button>

  <!-- Generating State -->
  <div v-if="generating" class="generating-panel">
    <!-- Step Progress Indicator -->
    <div class="gen-steps">
      <div v-for="(step, si) in genSteps" :key="si" class="gen-step" :class="{ active: genCurrentStep >= si, done: genCurrentStep > si }">
        <div class="gen-step-icon">
          <span v-if="genCurrentStep > si">✓</span>
          <span v-else>{{ step.i }}</span>
        </div>
        <div class="gen-step-label">{{ step.label }}</div>
      </div>
    </div>

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
        :class="state.status"
      >
        <div class="chapter-status-icon">
          <span v-if="state.status === 'completed'" class="status-check">✓</span>
          <span v-else-if="state.status === 'generating'" class="status-spinner"></span>
          <span v-else class="status-pending">○</span>
        </div>
        <div class="chapter-name">{{ state.name }}</div>
        <div class="chapter-status-tag" :class="state.status">
          {{ state.status === 'pending' ? '待生成' : state.status === 'generating' ? '生成中' : '已完成' }}
        </div>
        <div class="chapter-bar-wrap">
          <el-progress
            :percentage="state.progress"
            :status="state.status === 'completed' ? 'success' : undefined"
            :stroke-width="6"
            :show-text="false"
            :class="{ 'progress-striped': state.status === 'generating' }"
          />
        </div>
        <div class="chapter-pct">{{ state.progress }}%</div>
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
      <span class="done-icon">✅</span>
      标书生成成功
    </div>
    <button type="button" class="download-btn" @click="emit('download', generatedFile.name)">
      <el-icon><component :is="Download" /></el-icon>
      下载 {{ generatedFile.name }}
    </button>
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
</template>

<script setup>
import { Download, Files } from "@element-plus/icons-vue"

defineProps({
  selectedStrategy: { type: String, default: "综合均衡型" },
  generating: { type: Boolean, default: false },
  parseResult: { type: Object, default: null },
  selectedMaterials: { type: Array, default: () => [] },
  progress: { type: Number, default: 0 },
  progressMessage: { type: String, default: "" },
  genCurrentStep: { type: Number, default: 0 },
  chapterStates: { type: Object, default: () => ({}) },
  renderedContent: { type: String, default: "" },
  generatedFile: { type: Object, default: null },
  reviewResult: { type: Object, default: null },
  formatResult: { type: Object, default: null },
  violationResult: { type: Object, default: null },
  plagiarismResult: { type: Object, default: null },
})
const emit = defineEmits(["update:selectedStrategy", "generate", "download"])

const strategyOptions = [
  { label: "技术优先型", value: "技术优先型", icon: "🔧", desc: "技术方案详细、质量最高、价格适中" },
  { label: "成本控制型", value: "成本控制型", icon: "💰", desc: "价格最低方案，利润优先" },
  { label: "综合均衡型", value: "综合均衡型", icon: "⚖️", desc: "技术和价格平衡，性价比最优" },
]
const genSteps = [
  { i: "1", label: "解析" },
  { i: "2", label: "检测" },
  { i: "3", label: "生成" },
  { i: "4", label: "质检" },
  { i: "5", label: "完成" },
]
</script>

