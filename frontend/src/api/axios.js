import axios from "axios";
import NProgress from "nprogress";
import "nprogress/nprogress.css";

export const api = axios.create({
  baseURL: "http://localhost:8000/",
  withCredentials: true, // required for cookies
});

// Start NProgress on every request
api.interceptors.request.use((config) => {
  NProgress.start();
  return config;
});

// Token refresh handling
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error) => {
  failedQueue.forEach((p) => {
    if (error) p.reject(error);
    else p.resolve();
  });
  failedQueue = [];
};

// Response interceptor
api.interceptors.response.use(
  (response) => {
    NProgress.done();
    return response;
  },
  async (error) => {
    NProgress.done();
    const originalRequest = error.config;

    if (
      originalRequest.url.includes("/api/token/") &&
      !originalRequest.url.includes("/refresh")
    ) {
      return Promise.reject(error); // fail login normally
    }

    // Handle 401 errors for other requests
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(() => api(originalRequest));
      }

      isRefreshing = true;

      try {
        const tenant = window.location.pathname.split("/")[1] || "default";
        await api.post(`/${tenant}/api/token/refresh/`);

        processQueue(null);
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError);
        const tenant = window.location.pathname.split("/")[1] || "default";
        window.location.href = `/${tenant}/login`; // redirect to login
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;