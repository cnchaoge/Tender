<template>
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
            :class="{ 
              'disqualify-item': item.disqualify_if_fail,
              'formula-item': item.type === 'formula',
              'expert-item': item.type === 'expert'
            }"
          >
            <div class="scoring-item-row">
              <div class="scoring-item-left">
                <span v-if="item.disqualify_if_fail" class="scoring-disqualify-icon">🔴</span>
                <span class="scoring-item-name">{{ item.name }}</span>
              </div>
              <span class="scoring-item-score">{{ item.score }}/{{ item.max_score || item.score }}分</span>
            </div>
            <div class="scoring-item-meta">
              <span class="scoring-item-type" :class="item.type">
                <span class="type-icon">{{ scoringTypeIcon(item.type) }}</span>
                {{ scoringTypeLabel(item.type) }}
              </span>
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
</template>

<script setup>
import { ref } from "vue"
import { ArrowRight } from "@element-plus/icons-vue"

defineProps({
  parseResult: { type: Object, default: null },
})

const editingProjectName = ref(false)
const editingDeadline = ref(false)
const showRawText = ref(false)
const openScoringSections = ref(new Set())

function toggleScoringSection(idx) {
  if (openScoringSections.value.has(idx)) openScoringSections.value.delete(idx)
  else openScoringSections.value.add(idx)
}

function scoringTypeLabel(type) {
  const map = { expert: "专家打分", formula: "公式计算", qualified: "满足即得分" }
  return map[type] || type || "未知"
}

function scoringTypeIcon(type) {
  const map = { expert: "👤", formula: "🔢", qualified: "✓" }
  return map[type] || "📋"
}
</script>

