import axios from "axios"
import Nprogress from "nprogress"
import "nprogress/nprogress.css"

export const api = axios.create({
  baseURL: "http://localhost:8000/",
  withCredentials: true,
})

api.interceptors.request.use((config) => {
  Nprogress.start();
  return config;
});

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error) => {
  failedQueue.forEach(p => {
    if (error) p.reject(error);
    else p.resolve();
  });
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => {
    Nprogress.done();
    return response;
  },
  async (error) => {
    Nprogress.done();
    const originalRequest = error.config;

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
        window.location.href = `/${tenant}/login`;
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default api;