import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export function getApiErrorCode(err: any): string | undefined {
  return err.response?.data?.error?.code;
}

export function getApiErrorMessage(err: any, fallback: string): string {
  const data = err.response?.data;
  const message = data?.error?.message ?? data?.detail;
  return typeof message === "string" ? message : fallback;
}

export default client;
