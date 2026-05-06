import { defineStore } from "pinia"
import { ref, computed } from "vue"
import api from "../api"

export const useAuthStore = defineStore("auth", () => {
  const token = ref(localStorage.getItem("token") || "")
  const user = ref(JSON.parse(localStorage.getItem("user") || "null"))

  const isLoggedIn = computed(() => !!token.value)

  async function login(username, password) {
    const resp = await api.post("/api/auth/login", { username, password })
    token.value = resp.data.access_token
    user.value = resp.data.user
    localStorage.setItem("token", token.value)
    localStorage.setItem("user", JSON.stringify(user.value))
    api.defaults.headers.common["Authorization"] = `Bearer ${token.value}`
    return resp.data
  }

  function logout() {
    token.value = ""
    user.value = null
    localStorage.removeItem("token")
    localStorage.removeItem("user")
    delete api.defaults.headers.common["Authorization"]
  }

  // 初始化时设置 token
  if (token.value) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token.value}`
  }

  return { token, user, isLoggedIn, login, logout }
})
