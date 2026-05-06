import { defineStore } from "pinia"
import { ref } from "vue"
import api from "../api"

export const useKbStore = defineStore("kb", () => {
  const documents = ref([])
  const loading = ref(false)

  async function fetchDocuments() {
    loading.value = true
    try {
      const resp = await api.get("/api/kb/documents")
      documents.value = resp.data
    } finally {
      loading.value = false
    }
  }

  async function addFolder(folderPath) {
    const resp = await api.post("/api/kb/folder", null, {
      params: { folder_path: folderPath }
    })
    await fetchDocuments()
    return resp.data
  }

  async function deleteDocument(id) {
    await api.delete(`/api/kb/documents/${id}`)
    await fetchDocuments()
  }

  return { documents, loading, fetchDocuments, addFolder, deleteDocument }
})
