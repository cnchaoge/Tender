<template>
  <div class="bid-page">

    <div class="page-header">
      <div class="eyebrow">投标工具</div>
      <h1 class="page-title">标书生成</h1>
      <p class="page-desc">{{ projectHeadline }}</p>
    </div>

    <div class="bid-grid">
      <div class="section">
        <TenderUpload
          :bid-file="bidFile"
          :parse-result="parseResult"
          @file-selected="onFileSelected"
        />
        <ParseEditor :parse-result="parseResult" />
      </div>

      <div class="section">
        <OutlinePlan
          :templates="templates"
          :selected-template-id="selectedTemplateId"
          :selected-template="selectedTemplate"
          :plan-dialog-visible="planDialogVisible"
          :planning-chapters="planningChapters"
          @select="selectTemplate"
          @clear="clearTemplate"
          @update:plan-dialog-visible="planDialogVisible = $event"
          @confirm="confirmPlanAndGenerate"
        />
        <MaterialPicker
          :available-materials="availableMaterials"
          :selected-materials="selectedMaterials"
          :parse-result="parseResult"
          :match-check-result="matchCheckResult"
          :checking-match="checkingMatch"
          :show-upload-inline="showUploadInline"
          :uploading-inline="uploadingInline"
          @toggle="toggleMaterial"
          @update:show-upload-inline="showUploadInline = $event"
          @check-match="checkMatch"
          @inline-change="handleInlineFileSelected"
        />
        <GeneratePanel
          :selected-strategy="selectedStrategy"
          :generating="generating"
          :parse-result="parseResult"
          :selected-materials="selectedMaterials"
          :progress="progress"
          :progress-message="progressMessage"
          :gen-current-step="genCurrentStep"
          :chapter-states="chapterStates"
          :rendered-content="renderedContent"
          :generated-file="generatedFile"
          :review-result="reviewResult"
          :format-result="formatResult"
          :violation-result="violationResult"
          :plagiarism-result="plagiarismResult"
          @update:selected-strategy="selectedStrategy = $event"
          @generate="handleGenerate"
          @download="downloadBidFile"
        />
        <VersionHistory
          :version-list="versionList"
          :loading-versions="loadingVersions"
          :expanded-version-id="expandedVersionId"
          :version-contents="versionContents"
          :compare-dialog-visible="compareDialogVisible"
          :compare-from-id="compareFromId"
          :compare-to-id="compareToId"
          :compare-diff="compareDiff"
          :comparing="comparing"
          @toggle="toggleVersion"
          @regenerate="regenerateFromVersion"
          @open-compare="showCompareDialog"
          @compare="doCompare"
          @download="downloadBidFile"
          @update:compare-dialog-visible="compareDialogVisible = $event"
          @update:compare-from-id="compareFromId = $event"
          @update:compare-to-id="compareToId = $event"
        />
      </div>
    </div>

    <BidChecklistDialog
      v-model="showChecklistDialog"
      :bid-version-id="currentVersionId"
      :bid-content="streamingContent"
      :parse-result="parseResult"
      :project-id="activeProjectId"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { useKbStore } from "../stores/kb"
import { useWorkspaceStore } from "../stores/workspace"
import {
  queryProjectId,
  saveProjectSnapshot,
  setProjectMaterials,
  uploadTender,
} from "../features/projects/api"
import api, { bid, downloadWithAuth } from "../api"
import { marked } from "marked"
import BidChecklistDialog from "../components/BidChecklistDialog.vue"
import TenderUpload from "../features/generation/TenderUpload.vue"
import ParseEditor from "../features/generation/ParseEditor.vue"
import MaterialPicker from "../features/generation/MaterialPicker.vue"
import OutlinePlan from "../features/generation/OutlinePlan.vue"
import GeneratePanel from "../features/generation/GeneratePanel.vue"
import VersionHistory from "../features/generation/VersionHistory.vue"

// Configure marked for security (no async)
// Configure marked for security (no async)
marked.setOptions({ breaks: true, gfm: true })

const route = useRoute()
const router = useRouter()
const workspace = useWorkspaceStore()
const kbStore = useKbStore()
const activeProjectId = computed(() => queryProjectId(route.query) || workspace.projectId)
const baseline = ref({ project_name: "", deadline: "" })
let persistReady = false
let persistTimer = null

onMounted(async () => {
  await ensureProject()
  loadTemplates()
  loadVersions()
  kbStore.fetchDocuments().catch(() => {})
})
const bidFile = ref(null)
const bidDocId = ref(null)  // 上传的招标文件 doc_id，不参与素材选择
const parseResult = ref(null)
const projectHeadline = computed(() => {
  const name = parseResult.value?.project_name
  if (name && name !== "解析失败" && name !== "未识别到项目名称") return name
  return "上传招标文件，系统自动解析项目信息并生成完整投标标书"
})
const selectedMaterials = ref([])
const generating = ref(false)
const generatedFile = ref(null)
const generatedContent = ref("")
const currentVersionId = ref(null)
const showChecklistDialog = ref(false)
const reviewResult = ref(null)
const progress = ref(0)
const progressMessage = ref("")
const streamingContent = ref("")   // 原始 markdown 文本
const renderedContent = ref("")    // 渲染后的 HTML
const showUploadInline = ref(false)  // 内联上传区展开
const uploadingInline = ref(false)
const matchCheckResult = ref(null)  // 匹配度检测结果
const checkingMatch = ref(false)
const planningChapters = ref([])    // 规划阶段章节列表
const planDialogVisible = ref(false) // 规划阶段弹窗

// 模板选择
const templates = ref([])
const selectedTemplateId = ref(null)
const selectedTemplate = ref(null)
const loadingTemplates = ref(false)

async function loadTemplates() {
  loadingTemplates.value = true
  try {
    const resp = await api.get("/api/bid/templates")
    templates.value = resp.data.templates || []
  } catch {
    // 静默失败
  } finally {
    loadingTemplates.value = false
  }
}

function clearTemplate() {
  selectedTemplateId.value = null
  selectedTemplate.value = null
}

function selectTemplate(tpl) {
  if (selectedTemplateId.value === tpl.id) {
    clearTemplate()
    return
  }
  selectedTemplateId.value = tpl.id
  selectedTemplate.value = tpl
  // 同步策略选择
  if (tpl.default_strategy) {
    selectedStrategy.value = tpl.default_strategy
  }
}
const violationResult = ref(null)   // 废标项检测结果
const plagiarismResult = ref(null)   // 标书查重结果
const formatResult = ref(null)       // 格式检查结果

const selectedStrategy = ref("综合均衡型") // 默认选中

// Chapter progress state: Map<chapter_index, {name, status, progress}>
const chapterStates = ref({})

const genCurrentStep = ref(0)

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


// 素材列表：解析后显示推荐素材（带相关度），未解析时显示知识库全部文档（排除生成的 bid 文件）
const availableMaterials = computed(() => {
  const excludeId = bidDocId.value
  const recMap = {}
  for (const m of parseResult.value?.recommended_materials || []) {
    recMap[m.id] = m
  }
  const hasRecommended = Object.keys(recMap).length > 0
  const result = []
  for (const doc of kbStore.documents) {
    if (doc.id === excludeId) continue
    if (doc.filename.startsWith('bid_')) continue  // 排除生成的投标文件
    if (hasRecommended && !recMap[doc.id]) continue
    result.push(recMap[doc.id]
      ? { ...recMap[doc.id], file_type: doc.file_type, chunk_count: doc.chunk_count }
      : { id: doc.id, filename: doc.filename, file_type: doc.file_type, chunk_count: doc.chunk_count })
  }
  // 推荐模式下按相关度降序排列
  if (hasRecommended) {
    result.sort((a, b) => (b.relevance_score ?? 0) - (a.relevance_score ?? 0))
  }
  return result
})

function rememberBaseline(result) {
  baseline.value = {
    project_name: result?.project_name || "",
    deadline: result?.deadline || "",
  }
}

function applyProject(project) {
  const result = project?.parse?.result || null
  parseResult.value = result
  const docs = project?.documents || []
  const tenderId = project?.parse?.document_id
  const tender = docs.find((doc) => doc.role === "tender" && doc.document_id === tenderId)
    || docs.find((doc) => doc.role === "tender")
  if (tender) {
    bidFile.value = { name: tender.filename || "招标文件" }
    bidDocId.value = tender.document_id
  } else if (result) {
    bidFile.value = { name: "招标文件" }
    bidDocId.value = tenderId || null
  } else {
    bidFile.value = null
    bidDocId.value = null
  }
  selectedMaterials.value = [...(project?.material_ids || [])]
  rememberBaseline(result)
}

async function ensureProject() {
  persistReady = false
  let id = queryProjectId(route.query)
  if (!id && workspace.projectId) {
    id = workspace.projectId
    await router.replace({ path: "/bid", query: { project_id: String(id) } })
  }
  if (!id) {
    const created = await workspace.createProject({})
    id = created.id
    await router.replace({ path: "/bid", query: { project_id: String(id) } })
    applyProject(created)
    await nextTick()
    persistReady = true
    return
  }
  try {
    const project = await workspace.loadProject(id)
    applyProject(project)
  } catch {
    workspace.clear()
    const created = await workspace.createProject({})
    await router.replace({ path: "/bid", query: { project_id: String(created.id) } })
    applyProject(created)
  }
  await nextTick()
  persistReady = true
}

function schedulePersist() {
  if (!persistReady || !activeProjectId.value) return
  clearTimeout(persistTimer)
  persistTimer = setTimeout(persistProjectState, 400)
}

async function persistProjectState() {
  const id = activeProjectId.value
  if (!id) return
  try {
    if (parseResult.value) {
      const nameEdited = (parseResult.value.project_name || "") !== baseline.value.project_name
      const deadlineEdited = (parseResult.value.deadline || "") !== baseline.value.deadline
      await saveProjectSnapshot(id, {
        result: parseResult.value,
        name_edited: nameEdited,
        deadline_edited: deadlineEdited,
      })
      if (nameEdited || deadlineEdited) rememberBaseline(parseResult.value)
    }
    await setProjectMaterials(id, selectedMaterials.value)
  } catch {
    // 自动保存失败时保留页面上的内容，下次编辑再试。
  }
}

watch(parseResult, schedulePersist, { deep: true })
watch(selectedMaterials, schedulePersist, { deep: true })

async function loadVersions() {
  loadingVersions.value = true
  try {
    const params = activeProjectId.value
      ? { project_id: activeProjectId.value }
      : (parseResult.value?.project_name ? { project_name: parseResult.value.project_name } : {})
    const resp = await api.get("/api/bid/versions", { params })
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


async function downloadBidFile(filename) {
  if (!filename) return
  try {
    await downloadWithAuth(`/api/bid/download/${encodeURIComponent(filename)}`, filename)
  } catch (e) {
    if (e.status === 401) return
    ElMessage.error(e.message || "下载失败")
  }
}


async function onFileSelected(file) {
  if (!file) return
  const id = activeProjectId.value
  if (!id) {
    ElMessage.error("项目尚未就绪")
    return
  }
  persistReady = false
  const formData = new FormData()
  formData.append("file", file)
  try {
    const uploadResp = await uploadTender(id, formData)
    await kbStore.fetchDocuments()
    bidFile.value = file
    bidDocId.value = uploadResp.data.document_id
    const resp = await api.post("/api/bid/parse", {
      document_id: uploadResp.data.document_id,
      project_id: id,
    })
    parseResult.value = resp.data
    const recommended = resp.data.recommended_materials || []
    selectedMaterials.value = recommended.map(m => m.id)
    rememberBaseline(resp.data)
    await setProjectMaterials(id, selectedMaterials.value)
    ElMessage.success("招标文件解析完成" + (recommended.length ? `，已自动关联 ${recommended.length} 个相关素材` : ""))
    loadVersions()
  } catch {
    ElMessage.error("解析失败")
  } finally {
    await nextTick()
    persistReady = true
  }
}

function toggleMaterial(id) {
  const idx = selectedMaterials.value.indexOf(id)
  if (idx >= 0) selectedMaterials.value.splice(idx, 1)
  else selectedMaterials.value.push(id)
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
      materials: selectedMaterials.value,
      template_id: selectedTemplateId.value || null
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
  genCurrentStep.value = 1

  try {
    const response = await bid.openGenerateStream({
      parse_result: parseResult.value,
      materials: selectedMaterials.value,
      chapters: planningChapters.value,
      strategy: selectedStrategy.value,
      project_id: activeProjectId.value,
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
            // Trigger fade-in animation on new content
            const preview = document.querySelector('.streaming-html')
            if (preview) {
              preview.classList.remove('content-update')
              void preview.offsetWidth // reflow
              preview.classList.add('content-update')
            }
          }
          // Chapter-level events
          if (data.stage === "chapter_start") {
            genCurrentStep.value = 3 // 生成
            const idx = data.chapter_index
            if (chapterStates.value[idx] !== undefined) {
              chapterStates.value[idx] = { ...chapterStates.value[idx], status: "generating", progress: 0 }
            }
          }
          if (data.stage === "chapter_progress") {
            const idx = data.chapter_index
            if (chapterStates.value[idx] !== undefined) {
              chapterStates.value[idx] = { ...chapterStates.value[idx], progress: data.progress }
            }
          }
          if (data.stage === "chapter_done") {
            genCurrentStep.value = 4 // 质检
            const idx = data.chapter_index
            if (chapterStates.value[idx] !== undefined) {
              chapterStates.value[idx] = { ...chapterStates.value[idx], status: "completed", progress: 100 }
            }
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
            genCurrentStep.value = 2 // 检测
          }
          if (data.stage === "done") {
            genCurrentStep.value = 5 // 完成
            generatedFile.value = {
              name: data.filename,
            }
            reviewResult.value = data.review || null
            if (data.violation_result) violationResult.value = data.violation_result
            if (data.plagiarism_result) plagiarismResult.value = data.plagiarism_result
            if (data.format_result) formatResult.value = data.format_result
            // 刷新历史版本列表
            loadVersions()
            // 捕获 version_id 并自动弹出检查清单
            currentVersionId.value = data.version_id
            if (currentVersionId.value) {
              showChecklistDialog.value = true
            }
          }
        } catch {}
      }
    }
    if (generatedFile.value) ElMessage.success("标书生成成功")
    else ElMessage.error("生成失败")
  } catch (e) {
    if (e.status === 401) return
    ElMessage.error(e.response?.data?.detail || e.message || "生成失败")
  } finally {
    generating.value = false
  }
}
</script>

<style src="../features/generation/bid-page.css"></style>
