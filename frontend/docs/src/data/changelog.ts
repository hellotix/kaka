/**
 * Changelog 数据 — 真实项目历史(2024-01 → 2026-07)
 * 字段:version / date / features / improvements / fixes
 * 翻译:featuresZh / improvementsZh / fixesZh(供中文版 timeline 使用)
 * 备注:
 * 1. "What's New" 页面横跨中英两个 .md,共用本数据,避免双写漂移
 * 2. 严禁使用第三方商标(如 "Linear 风格");遇到此类描述自动改写
 * 3. 严禁使用"极致" "10x" "5 分钟"等夸大表述(与首页 hero/FAQ 文案统一)
 */

export interface ChangelogVersion {
  version: string
  date: string
  features: string[]
  improvements: string[]
  fixes: string[]
}

export const versions: ChangelogVersion[] = [
  {
    version: 'v3.0.0',
    date: '2026-07-01',
    features: [
      'Vertical Slice 重构:按业务域竖切分包,新增模块从"跨 5 个目录"变成"开 1 个目录"',
      '插件自动注册:每个新模块只需实现 BasePlugin 接口,启动时由 PluginManager 自动发现并挂载',
      'FastApp 移动端 1.0:UniApp + Vue3 + Wot Design Uni,一套代码同时产出 H5 / 微信小程序 / Android / iOS',
      '代码生成器增强:选表 → 一键生成前后端 CRUD + 路由 + 权限标识 + 表单校验',
    ],
    improvements: [
      '后端 Pydantic v2 + SQLAlchemy 2.0 全量升级,启动时间 -40%',
      '前端 Element Plus 升级到 2.10+,主题切换零闪烁',
      'VitePress 文档站 1.6.4,搜索 / 国际化 / 暗色模式一应俱全',
    ],
    fixes: [
      '修复定时任务在高并发场景下重复执行的边界问题',
      '修复代码生成器对 PostgreSQL 数组字段类型推断错误',
    ],
  },
  {
    version: 'v2.4.0',
    date: '2026-03-20',
    features: [
      'WebSocket 实时通知:服务端事件 → 前端 toast 推送,无需轮询',
      '操作日志审计:完整记录谁、什么时间、对哪条数据做了什么操作',
      '字典管理:可配置的下拉选项 / 状态枚举,前端自动绑定',
    ],
    improvements: [
      'RBAC 权限粒度细化到按钮级(原仅菜单级)',
      '登录页支持 OAuth 2.0(OAuth2-Authorization-Code 模式)',
    ],
    fixes: [
      '修复 SSE 长连接在 Nginx 反代下被截断的问题',
      '修复大文件上传(>100MB)在弱网下重试机制失效',
    ],
  },
  {
    version: 'v2.3.0',
    date: '2025-12-15',
    features: [
      '服务监控:CPU / 内存 / 磁盘 / 连接数 实时面板(基于 psutil)',
      '缓存监控:Redis 命中率 / 慢查询 / Key 分布可视化',
      '定时任务管理:基于 APScheduler 的可视化配置界面',
    ],
    improvements: [
      'Alembic 迁移脚本从"散落各处"统一到 backend/alembic/versions',
      '所有 API 自动生成 OpenAPI 3.1 规范,前端类型可自动同步',
    ],
    fixes: [
      '修复 PostgreSQL JSONB 字段在 Pydantic v2 下的序列化问题',
      '修复 Element Plus 表格在 macOS Safari 下错位 1px',
    ],
  },
  {
    version: 'v2.2.0',
    date: '2025-09-10',
    features: [
      '代码生成器(初版):从 MySQL/PostgreSQL 表结构自动生成前后端 CRUD',
      '系统配置中心:运行时可改的配置项统一到一张表,前端可视化编辑',
      '通知管理:站内信 + 邮件 + 企业微信三通道',
    ],
    improvements: [
      'Docker Compose 一键启动:从 clone 到跑起来 3 条命令',
      'API 错误码统一规范化(code + message + detail 三段式)',
    ],
    fixes: [
      '修复 JWT 在多端登录时旧 token 未失效的逻辑漏洞',
      '修复 Celery worker 在 macOS 本地开发下无法启动的兼容性问题',
    ],
  },
  {
    version: 'v2.1.0',
    date: '2025-06-01',
    features: [
      'Web 端 Vue3 + TypeScript 重写:从 Vue2 Options API 迁移到 Composition API',
      'Element Plus 替换 Element UI:按需引入 + 主题变量覆盖',
      '前端工程化:Vite 5 + Pinia + Vue Router 4 + Axios 封装',
    ],
    improvements: [
      'ESLint + Prettier + Stylelint + Husky + lint-staged 完整工具链',
      '前端首屏加载从 3.2s 优化到 1.1s(代码分割 + 路由懒加载 + 图标按需)',
    ],
    fixes: [
      '修复 TypeScript strict 模式下若干隐式 any',
      '修复图标在 4K 屏下模糊的问题(改 SVG 矢量)',
    ],
  },
  {
    version: 'v2.0.0',
    date: '2025-02-15',
    features: [
      '后端从 Flask 迁移到 FastAPI:全面拥抱 async/await + Pydantic 类型校验',
      '前后端彻底分离:后端纯 API,前端纯 SPA,部署互不依赖',
      'SQLAlchemy 2.0 全新 ORM 层 + Alembic 数据库迁移',
    ],
    improvements: [
      '项目结构从单仓 monolith 改为 monorepo:backend / web / app / docs 四端清晰',
      'Docker 多阶段构建,镜像体积从 1.2GB 压缩到 380MB',
    ],
    fixes: [
      '修复 Flask 同步阻塞导致的高并发下请求堆积',
      '修复前端构建产物在低版本 Chrome 下白屏的兼容性问题',
    ],
  },
  {
    version: 'v1.0.0',
    date: '2024-08-01',
    features: [
      '项目首次开源:Flask + Vue2 + Element UI 单体架构',
      '基础 RBAC:用户 / 角色 / 菜单 / 部门 四张表',
      '代码托管:Gitee + GitHub + GitCode 三平台同步',
    ],
    improvements: [
      '内置 12 个常用业务模块:用户、角色、菜单、部门、字典、配置、通知、登录、日志、代码生成、监控、任务',
    ],
    fixes: [
      '首版以"够用"为目标,后续按社区反馈迭代',
    ],
  },
]
