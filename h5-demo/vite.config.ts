import { defineConfig } from 'vite'

// 本文件由 Vite 自己用 esbuild 加载，不参与 `tsc --noEmit`（tsconfig 的 include 只有 src）。
export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 开发期把 /api 原样转发给后端，浏览器眼里前后端同源，天然绕开 CORS。
      // 后端路由前缀是 /api/v1（见 backend/app/config/setting.py 的 ROOT_PATH），
      // 因此不做路径重写：
      //   /api/v1/app/login/password  →  http://127.0.0.1:8001/api/v1/app/login/password
      // changeOrigin 让后端 request.base_url 是 127.0.0.1:8001，
      // 上传接口据此拼出的图片绝对 URL（/static/upload/...）才能被 <img> 直接加载。
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
