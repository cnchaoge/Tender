<template>
  <div class="bid-page">
    <el-row :gutter="20">
      <!-- 左侧：招标文件 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>招标文件</span>
          </template>

          <el-upload
            :http-request="handleUploadBid"
            :show-file-list="false"
            accept=".pdf,.docx"
            style="margin-bottom: 16px"
          >
            <el-button type="primary">
              <el-icon><component :is="Upload" /></el-icon>
              上传招标文件
            </el-button>
          </el-upload>

          <div v-if="bidFile" class="bid-file-info">
            <el-icon><component :is="Document" /></el-icon>
            {{ bidFile.name }}
          </div>

          <div v-if="parseResult && parseResult.project_name !== '解析失败'">
            <el-divider>解析结果</el-divider>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="项目名称">
                {{ parseResult.project_name }}
              </el-descriptions-item>
              <el-descriptions-item label="工期">
                {{ parseResult.deadline || "未提取到" }}
              </el-descriptions-item>
              <el-descriptions-item label="资格要求">
                <el-tag
                  v-for="r in parseResult.requirements"
                  :key="r"
                  size="small"
                  style="margin-right: 4px"
                >
                  {{ r }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="资质要求">
                <el-tag
                  v-for="r in parseResult.qualification"
                  :key="r"
                  size="small"
                  type="success"
                  style="margin-right: 4px"
                >
                  {{ r }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：素材选择 + 生成 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>素材选择</span>
          </template>

          <el-checkbox-group v-model="selectedMaterials">
            <el-checkbox
              v-for="doc in kbStore.documents"
              :key="doc.id"
              :label="doc.id"
              style="display: block; margin-bottom: 8px"
            >
              {{ doc.filename }}
            </el-checkbox>
          </el-checkbox-group>

          <div v-if="!kbStore.documents.length" style="color: #c0c4cc; font-size: 13px">
            知识库暂无文档，请先上传
          </div>
        </el-card>

        <el-card style="margin-top: 20px">
          <template #header>
            <span>生成标书</span>
          </template>

          <el-button
            type="primary"
            style="width: 100%"
            :loading="generating"
            :disabled="!parseResult || selectedMaterials.length === 0"
            @click="handleGenerate"
          >
            <el-icon><component :is="Files" /></el-icon>
            生成投标标书
          </el-button>

          <div v-if="generatedFile" style="margin-top: 12px">
            <el-alert type="success" :closable="false">
              标书已生成：
              <a :href="generatedFile.url" target="_blank">{{ generatedFile.name }}</a>
            </el-alert>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { Upload, Document, Files } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"
import api from "../api"

const kbStore = useKbStore()
const bidFile = ref(null)
const parseResult = ref(null)
const selectedMaterials = ref([])
const generating = ref(false)
const generatedFile = ref(null)

onMounted(() => kbStore.fetchDocuments())

async function handleUploadBid({ file }) {
  bidFile.value = file
  const formData = new FormData()
  formData.append("file", file)

  const uploadResp = await api.post("/api/kb/documents", formData, {
    headers: { "Content-Type": "multipart/form-data" }
  })
  await kbStore.fetchDocuments()

  try {
    const resp = await api.post("/api/bid/parse", {
      file_path: uploadResp.data.file_path
    })
    parseResult.value = resp.data
    ElMessage.success("招标文件解析完成")
  } catch (e) {
    ElMessage.error("解析失败")
  }
}

async function handleGenerate() {
  generating.value = true
  try {
    const resp = await api.post("/api/bid/generate", {
      parse_result: parseResult.value,
      materials: selectedMaterials.value
    })
    const filename = resp.data.filename
    generatedFile.value = {
      name: filename,
      url: `${api.defaults.baseURL}/api/bid/download/${filename}`
    }
    ElMessage.success("标书生成成功")
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "生成失败")
  } finally {
    generating.value = false
  }
}
</script>

<style scoped>
.bid-file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 14px;
  color: #606266;
}
</style>
