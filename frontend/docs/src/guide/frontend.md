---
layout: doc
title: 前端开发指南
description: FastApiAdmin 前端开发指南,Vue3 + TypeScript + Element Plus + Vite 技术栈的目录结构、组件封装、Pinia 状态管理、Axios 封装与 API 接入。
outline: "deep"
---

> 项目结构、路径别名、环境变量等详细说明见 [frontend/web/README.md](https://github.com/fastapiadmin/FastapiAdmin/blob/master/frontend/web/README.md)。

## 技术栈

| 类别 | 选型 |
|------|------|
| 框架 | Vue 3（Composition API / `<script setup>`） |
| 构建 | Vite 7 |
| 语言 | TypeScript |
| UI | Element Plus |
| 路由 | Vue Router 4（Hash 模式） |
| 状态 | Pinia + pinia-plugin-persistedstate |
| 样式 | Tailwind CSS 4、SCSS |
| HTTP | Axios |

## 项目结构

```
frontend/web/src/
├── api/              # 按业务模块划分的接口封装
├── assets/           # 图片、字体、全局样式等
├── components/       # 通用与业务组件
├── config/           # 应用配置
├── enums/            # 枚举
├── hooks/            # 组合式函数
├── layouts/          # 布局系统（左侧、顶部、混合）
├── locales/          # 国际化
├── plugins/          # Vue 插件注册
├── router/           # 静态路由、动态路由、守卫
├── store/            # Pinia 模块
├── styles/           # 样式系统（含暗色主题）
├── types/            # TypeScript 类型
├── utils/            # 工具函数
├── views/            # 页面视图
├── App.vue
└── main.ts           # 入口
```

## 路径别名

| 别名 | 指向 |
|------|------|
| `@` | `src/` |
| `@views` | `src/views` |
| `@stores` | `src/store` |
| `@utils` | `src/utils` |

## 环境变量

只有以 `VITE_` 开头的变量会注入前端代码：

| 变量 | 作用 |
|------|------|
| `VITE_PORT` | 开发服务器端口 |
| `VITE_API_BASE_URL` | 代理目标：后端 HTTP 根地址 |
| `VITE_APP_BASE_API` | 接口路径前缀 |
| `VITE_APP_WS_ENDPOINT` | WebSocket 地址 |
| `VITE_APP_TITLE` | 页面标题 |
| `VITE_BASE_URL` | 部署基础路径 |
| `VITE_ACCESS_MODE` | 菜单来源（frontend / backend / mixed） |

修改 env 后需**重启** `pnpm dev`。

## 启动与脚本

```bash
cd frontend/web
pnpm install
pnpm dev              # 开发服务器（默认 5173）

# 其他脚本
pnpm build            # 生产构建
pnpm type-check       # TypeScript 检查
pnpm lint             # ESLint + Prettier + Stylelint
pnpm clean:cache      # 清理缓存
```

## 路由与菜单

| 文件 | 职责 |
|------|------|
| `src/router/staticRoutes.ts` | 静态路由、壳层 |
| `src/router/dynamicRoutes.ts` | 菜单驱动的动态路由 |
| `src/router/beforeEach.ts` | 权限守卫、动态挂载 |
| `src/router/MenuProcessor.ts` | 后端菜单 → 前端路由 |

路由采用 **Hash 模式**，静态路由（Layout/登录/404）首屏注册，业务路由由守卫根据菜单权限延迟 `addRoute`。

## 应用启动流程

```
main.ts → initPlugins(app) → mount("#app")
  → App.vue → onBeforeMount: 主题初始化
  → onMounted: bootstrap() → 存储检查/版本升级/站点配置
  → 路由守卫 beforeEach
    → 存储失效检测
    → 登录态校验
    → 动态路由注册（菜单 → addRoute）
    → 标签/标题同步
```

## 与后端联调

1. 后端启动在 `http://127.0.0.1:8001`
2. `.env.development` 中 `VITE_API_BASE_URL` 配置正确
3. Vite `server.proxy` 将 `VITE_APP_BASE_API`（如 `/api/v1`）转发到后端

## 新增页面流程

1. 在 `src/api/` 创建对应 API 文件
2. 在 `src/views/` 创建页面组件
3. 路由注册（静态或动态路由）+ 后端菜单配置
4. 路径与 name 保持三者一致

## 常见问题

| 现象 | 建议 |
|------|------|
| `ECONNREFUSED` | 后端未启动或端口错误 |
| 401 / 频繁跳转登录 | Token 失效，清除本地存储重新登录 |
| 修改 `.env` 不生效 | 必须重启 `pnpm dev` |
| 依赖异常 | 尝试 `pnpm clean:cache && pnpm dev` |
| 类型报错 | `pnpm type-check` 检查 |

## 构建与部署

- 输出目录：`dist/`
- 子路径部署时配置 `VITE_BASE_URL`
- 生产构建会移除部分 `console`（见 `vite.config.ts`）
