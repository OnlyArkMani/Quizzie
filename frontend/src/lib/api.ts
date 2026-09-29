import axios from "axios";
import { useAuthStore } from "@/features/auth/store/authStore";

// Relative path → goes through Vite proxy in dev, nginx proxy in prod. No CORS.
const baseURL = "/api/v1";

const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor: attach JWT from Zustand store (no localStorage parsing) ──
api.interceptors.request.use(
  (config) => {
    // useAuthStore.getState() is the correct way to access Zustand outside React
    const token = useAuthStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor: on 401 log out cleanly via the store ──
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Call the store's logout action — updates state AND clears localStorage
      useAuthStore.getState().logout({ revokeOnServer: false });
      // Only redirect if we're not already on a public page
      const publicPaths = ["/login", "/register", "/verify-email", "/forgot-password", "/reset-password"];
      if (!publicPaths.some((p) => window.location.pathname.startsWith(p))) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
