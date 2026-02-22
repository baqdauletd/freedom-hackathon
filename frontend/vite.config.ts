import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// https://vite.dev/config/
const apiProxy = {
  target: "http://localhost:8000",
  changeOrigin: true,
}

export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [["babel-plugin-react-compiler"]],
      },
    }),
  ],
  server: {
    proxy: {
      "/route": apiProxy,
      "/tickets": apiProxy,
      "/runs": apiProxy,
      "/results": apiProxy,
      "/managers": apiProxy,
      "/assistant": apiProxy,
      "/analytics": apiProxy,
      "/health": apiProxy,
      "/openapi.json": apiProxy,
    },
  },
  preview: {
    proxy: {
      "/route": apiProxy,
      "/tickets": apiProxy,
      "/runs": apiProxy,
      "/results": apiProxy,
      "/managers": apiProxy,
      "/assistant": apiProxy,
      "/analytics": apiProxy,
      "/health": apiProxy,
      "/openapi.json": apiProxy,
    },
  },
})
