const trimSlash = (value: string) => value.replace(/\/$/, "")

const rawBaseUrl = (import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE || "") as
  | string
  | undefined

export const API_BASE_URL = trimSlash(rawBaseUrl || "")

export const toApiUrl = (path: string): string => {
  if (path.startsWith("http")) return path
  if (!API_BASE_URL) return path
  return `${API_BASE_URL}/${path.replace(/^\//, "")}`
}
