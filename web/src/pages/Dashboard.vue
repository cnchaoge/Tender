<template>
  <div class="dashboard">
    <el-row :gutter="20">
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #409eff20; color: #409eff">
            <el-icon><component :is="Document" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.document_count }}</div>
            <div class="stat-label">文档数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #67c23a20; color: #67c23a">
            <el-icon><component :is="Tickets" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.chunk_count }}</div>
            <div class="stat-label">切片数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #e6a23c20; color: #e6a23c">
            <el-icon><component :is="User" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.user_count }}</div>
            <div class="stat-label">用户数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card">
          <div class="stat-icon" style="background: #f56c6c20; color: #f56c6c">
            <el-icon><component :is="Cpu" /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ modelStatus }}</div>
            <div class="stat-label">AI 模型</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="16">
        <el-card>
          <template #header>
            <span>快速开始</span>
          </template>
          <div class="quick-actions">
            <el-button type="primary" @click="$router.push('/kb')">
              <el-icon><component :is="Upload" /></el-icon>
              上传文档
            </el-button>
            <el-button type="success" @click="$router.push('/chat')">
              <el-icon><component :is="ChatDotRound" /></el-icon>
              开始问答
            </el-button>
            <el-button type="warning" @click="$router.push('/bid')">
              <el-icon><component :is="Tickets" /></el-icon>
              生成标书
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>系统信息</span>
          </template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="版本">v1.0.0</el-descriptions-item>
            <el-descriptions-item label="部署方式">本地部署</el-descriptions-item>
            <el-descriptions-item label="向量库">ChromaDB</el-descriptions-item>
            <el-descriptions-item label="AI 模型">DeepSeek</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { Document, Tickets, User, Cpu, Upload, ChatDotRound } from "@element-plus/icons-vue"
import api from "../api"

const stats = ref({ document_count: 0, chunk_count: 0, user_count: 0 })
const modelStatus = ref("未配置")

onMounted(async () => {
  try {
    const resp = await api.get("/api/admin/stats")
    stats.value = resp.data
    modelStatus.value = "DeepSeek"
  } catch (e) {
    // 服务可能未启动
  }
})
</script>

<style scoped>
.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #303133;
}

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}

.quick-actions {
  display: flex;
  gap: 12px;
}
</style>
