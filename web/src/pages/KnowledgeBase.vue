<template>
  <div class="kb-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>知识库文档</span>
          <div class="folder-input">
            <el-input
              v-model="folderPath"
              placeholder="输入文件夹路径，如 C:\Documents"
              style="width: 320px; margin-right: 8px"
            />
            <el-button type="primary" :loading="loading" @click="handleAddFolder">
              <el-icon><component :is="FolderAdd" /></el-icon>
              添加文件夹
            </el-button>
          </div>
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
        <el-table-column prop="created_at" label="添加时间" width="180" />
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
import { FolderAdd, Delete } from "@element-plus/icons-vue"
import { useKbStore } from "../stores/kb"

const kbStore = useKbStore()
const folderPath = ref("")
const loading = ref(false)

onMounted(() => kbStore.fetchDocuments())

function statusType(status) {
  return { ready: "success", processing: "warning", error: "danger" }[status] || "info"
}

async function handleAddFolder() {
  if (!folderPath.value.trim()) {
    ElMessage.warning("请输入文件夹路径")
    return
  }
  loading.value = true
  try {
    await kbStore.addFolder(folderPath.value.trim())
    ElMessage.success("添加成功")
    folderPath.value = ""
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "添加失败")
  } finally {
    loading.value = false
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
  flex-wrap: wrap;
  gap: 8px;
}
.folder-input {
  display: flex;
  align-items: center;
}
</style>
