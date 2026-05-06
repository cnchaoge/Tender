<template>
  <div class="kb-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>知识库文档</span>
          <el-upload
            :http-request="handleUpload"
            :show-file-list="false"
            accept=".pdf,.docx,.md,.txt"
          >
            <el-button type="primary" :loading="uploading">
              <el-icon><component :is="Upload" /></el-icon>
              上传文档
            </el-button>
          </el-upload>
        </div>
      </template>

      <el-table :data="kbStore.documents" v-loading="kbStore.loading" stripe>
        <el-table-column prop="filename" label="文件名" />
        <el-table-column prop="file_type" label="类型" width="80" />
        <el-table-column prop="chunk_count" label="切片数" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="180" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row.id)"
            >
              <el-icon><component :is="Delete" /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Upload, Delete } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"

const kbStore = useKbStore()
const uploading = ref(false)

onMounted(() => kbStore.fetchDocuments())

function statusType(status) {
  return { ready: "success", processing: "warning", error: "danger" }[status] || "info"
}

async function handleUpload({ file }) {
  uploading.value = true
  try {
    await kbStore.uploadDocument(file)
    ElMessage.success("上传成功")
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "上传失败")
  } finally {
    uploading.value = false
  }
}

async function handleDelete(id) {
  await ElMessageBox.confirm("确认删除此文档？", "提示", { type: "warning" })
  try {
    await kbStore.deleteDocument(id)
    ElMessage.success("删除成功")
  } catch (e) {
    ElMessage.error("删除失败")
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
