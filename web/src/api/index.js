import axios from "axios"

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "http://localhost:8000",
  timeout: 60000
})

// 响应拦截
api.interceptors.response.use(
  resp => resp,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token")
      localStorage.removeItem("user")
      window.location.href = "/login"
    }
    return Promise.reject(err)
  }
)

export default api
