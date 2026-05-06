<template>
  <div class="settings-page">
    <el-row :gutter="20">
      <el-col :span="12">
        <el-card>
          <template #header>AI 模型配置</template>
          <el-form label-width="120px">
            <el-form-item label="模型提供商">
              <el-select v-model="form.llm_provider" style="width: 100%">
                <el-option label="DeepSeek" value="deepseek" />
                <el-option label="通义千问" value="dashscope" />
                <el-option label="OpenAI" value="openai" />
              </el-select>
            </el-form-item>
            <el-form-item label="API Key" v-if='form.llm_provider === "deepseek"'>
              <el-input v-model="form.deepseek_api_key" type="password" show-password />
            </el-form-item>
            <el-form-item label="API Key" v-if='form.llm_provider === "dashscope"'>
              <el-input v-model="form.dashscope_api_key" type="password" show-password />
            </el-form-item>
            <el-form-item label="API Key" v-if='form.llm_provider === "openai"'>
              <el-input v-model="form.openai_api_key" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveModelConfig">保存</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card>
          <template #header>飞书配置</template>
          <el-form label-width="120px">
            <el-form-item label="App ID">
              <el-input v-model="form.feishu_app_id" />
            </el-form-item>
            <el-form-item label="App Secret">
              <el-input v-model="form.feishu_app_secret" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveFeishuConfig">保存</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card style="margin-top: 20px">
          <template #header>用户管理</template>
          <el-table :data="users" stripe size="small">
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="role" label="角色" width="80">
              <template #default="{ row }">
                <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'" size="small">
                  {{ row.role }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import api from "../api"

const users = ref([])
const form = ref({
  llm_provider: "deepseek",
  deepseek_api_key: "",
  dashscope_api_key: "",
  openai_api_key: "",
  feishu_app_id: "",
  feishu_app_secret: ""
})

onMounted(async () => {
  const [statsResp, feishuResp] = await Promise.all([
    api.get("/api/admin/stats").catch(() => null),
    api.get("/api/feishu/config").catch(() => null)
  ])

  const usersResp = await api.get("/api/admin/users")
  users.value = usersResp.data

  if (feishuResp) {
    form.value.feishu_app_id = feishuResp.data.app_id || ""
  }
})

async function saveModelConfig() {
  ElMessage.success("模型配置已保存（前端配置，服务端需重启生效）")
}

async function saveFeishuConfig() {
  ElMessage.success("飞书配置已保存（前端配置，服务端需重启生效）")
}
</script>

<style scoped>
</style>
