import { defineStore } from "pinia"
import { ref } from "vue"
import { kb as kbApi } from "../api"

const POLL_INTERVAL_MS = 1000
const MAX_POLL_ERRORS = 5

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export const useKbStore = defineStore("kb", () => {
  const documents = ref([])
  const loading = ref(false)
  const jobs = ref([])
  const pollers = new Map()

  async function fetchDocuments() {
    loading.value = true
    try {
      const resp = await kbApi.list()
      documents.value = resp.data
    } finally {
      loading.value = false
    }
  }

  function applyStatus(docId, data) {
    const doc = documents.value.find((item) => item.id === docId)
    if (doc) {
      doc.status = data.status
      doc.chunk_count = data.chunk_count
    }
    const job = jobs.value.find((item) => item.docId === docId)
    if (job) {
      job.status = data.status
      job.chunkCount = data.chunk_count || 0
    }
  }

  async function fetchStatus(docId) {
    const resp = await kbApi.status(docId)
    applyStatus(docId, resp.data)
    return resp.data
  }

  function removeJob(docId) {
    jobs.value = jobs.value.filter((job) => job.docId !== docId)
  }

  function removeSettledJob(docId) {
    jobs.value = jobs.value.filter((job) => {
      if (job.docId !== docId) return true
      return job.status === "pending" || job.status === "processing"
    })
  }

  async function pollLoop(docId) {
    let errors = 0
    try {
      while (errors < MAX_POLL_ERRORS) {
        try {
          const data = await fetchStatus(docId)
          errors = 0
          if (data.status === "ready" || data.status === "failed") {
            setTimeout(() => removeSettledJob(docId), 6000)
            return data
          }
        } catch (err) {
          if (err?.response?.status === 404) {
            removeJob(docId)
            return null
          }
          errors += 1
        }
        await sleep(POLL_INTERVAL_MS)
      }
      return null
    } finally {
      pollers.delete(docId)
    }
  }

  function trackJob(docId, filename, status = "pending") {
    const existing = jobs.value.find((job) => job.docId === docId)
    if (existing) {
      existing.filename = filename || existing.filename
      if (status) existing.status = status
    } else {
      jobs.value.push({
        docId,
        filename: filename || `文档 #${docId}`,
        status,
        chunkCount: 0,
      })
    }
    if (!pollers.has(docId)) {
      pollers.set(docId, pollLoop(docId))
    }
    return pollers.get(docId)
  }

  function watchDocument(doc) {
    if (!doc) return null
    if (doc.status === "pending" || doc.status === "processing") {
      return trackJob(doc.id, doc.filename, doc.status)
    }
    return null
  }

  async function addFolder(folderPath) {
    const resp = await kbApi.folder(folderPath)
    await fetchDocuments()
    const docs = Array.isArray(resp.data) ? resp.data : []
    for (const doc of docs) {
      watchDocument(doc)
    }
    return docs
  }

  async function deleteDocument(id) {
    await kbApi.delete(id)
    removeJob(id)
    await fetchDocuments()
  }

  async function uploadDocument(formData) {
    const resp = await kbApi.upload(formData)
    await fetchDocuments()
    const data = resp.data
    if (data.status === "pending" || data.status === "processing") {
      const doc = documents.value.find((item) => item.id === data.doc_id)
      trackJob(data.doc_id, doc?.filename || "", data.status)
    }
    return data
  }

  return {
    documents,
    loading,
    jobs,
    fetchDocuments,
    fetchStatus,
    trackJob,
    watchDocument,
    addFolder,
    uploadDocument,
    deleteDocument,
  }
})
