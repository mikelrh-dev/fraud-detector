import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor: attach JWT token from store
apiClient.interceptors.request.use((config) => {
  // Dynamic import to avoid circular dependency
  const token = localStorage.getItem("auth-storage");
  if (token) {
    try {
      const parsed = JSON.parse(token);
      const accessToken = parsed?.state?.token;
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`;
      }
    } catch {
      // Ignore parse errors
    }
  }
  return config;
});

// Response interceptor: redirect to login on 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      !error.config?.url?.includes("/auth/login")
    ) {
      localStorage.removeItem("auth-storage");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

export default apiClient;
