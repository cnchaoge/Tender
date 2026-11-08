import { ref } from "vue"
import { defineStore } from "pinia"
import { createProject as createProjectReq, getProject } from "../features/projects/api"

const STORAGE_KEY = "tender.projectId"

function readStoredId() {
  try {
    const id = Number(sessionStorage.getItem(STORAGE_KEY))
    return Number.isFinite(id) && id > 0 ? id : null
  } catch {
    return null
  }
}

export const useWorkspaceStore = defineStore("workspace", () => {
  const projectId = ref(readStoredId())
  const project = ref(null)

  function remember(id) {
    const next = Number(id)
    if (!Number.isFinite(next) || next <= 0) {
      projectId.value = null
      project.value = null
      try { sessionStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
      return
    }
    projectId.value = next
    try { sessionStorage.setItem(STORAGE_KEY, String(next)) } catch { /* ignore */ }
  }

  function clear() {
    remember(null)
  }

  async function loadProject(id) {
    const resp = await getProject(id)
    project.value = resp.data
    remember(resp.data.id)
    return resp.data
  }

  async function createProject(body = {}) {
    const resp = await createProjectReq(body)
    project.value = resp.data
    remember(resp.data.id)
    return resp.data
  }

  return { projectId, project, remember, clear, loadProject, createProject }
})
