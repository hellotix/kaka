<div align="center">
  <p align="center">
    <img src="src/static//logo.png" width="200" />
  </p>
  <h1 align="center">
    FastApp
    <sup style="background-color: #28a745; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.4em; vertical-align: super; margin-left: 5px;">v3.1.0</sup>
  </h1>
  <p align="center">
    基于 uni-app + Vue 3 + TypeScript 的现代化移动端跨平台开发模板
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/Vue-3.5.22-green.svg" alt="Vue">
    <img src="https://img.shields.io/badge/TypeScript-5.9.2-blue.svg" alt="TypeScript">
    <img src="https://img.shields.io/badge/uni--app-3.0.0-orange.svg" alt="uni-app">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  </p>
</div>

> **与仓库根文档的关系**：项目总览、一键前后端启动、演示账号、Docker 部署等请以 [根目录 README.md](../../README.md) 为准；**本文档**侧重 `frontend/app/` 移动端开发说明。

## 项目介绍

FastApp 是 FastapiAdmin 项目的移动端应用，基于 uni-app 框架开发，支持一套代码多端运行。采用 Vue 3 + TypeScript + Vite 等现代化技术栈，集成了完善的代码规范和开发工具链，为开发者提供开箱即用的移动端开发解决方案。

## 特性

- ⚡️ [Vue 3](https://github.com/vuejs/core), [Vite](https://github.com/vitejs/vite), [pnpm](https://pnpm.io/), [esbuild](https://github.com/evanw/esbuild) - 就是快！

- 🐂 [Wot UI V2](https://github.com/wot-ui/wot-ui) - 一个轻量、美观、AI友好的 uni-app 组件库

- 🚦 [@wot-ui/router](https://github.com/wot-ui/my-uni) - 适用于uni-app&vue3的轻量级路由库

- 🔄 [Uni Mini CI](https://github.com/Moonofweisheng/uni-mini-ci) - 一个小程序端持续集成的插件

- 🌐 [Alova](https://alova.js.org/zh-CN/) - 极致高效的请求工具集

- 🆒 [Uni Ku](https://uni-ku.js.org/) - 非常酷的 uni-app 插件库

- 📊 [Uni Echarts](https://uni-echarts.xiaohe.ink/) - 适用于 uni-app 的 Apache ECharts 组件

- 🎨 [UnoCSS](https://github.com/unocss/unocss) - 高性能且极具灵活性的即时原子化 CSS 引擎

- 😃 [各种图标集为你所用](https://github.com/antfu/unocss/tree/main/packages/preset-icons)

- 🔥 使用 [新的 `<script setup>` 语法](https://github.com/vuejs/rfcs/pull/227)

- 📥 [API 自动加载](https://github.com/antfu/unplugin-auto-import) - 直接使用 Composition API 无需引入

- 🦾 [TypeScript](https://www.typescriptlang.org/) & [ESLint](https://eslint.org/) - 保证代码质量

## 项目结构

```bash
src/
├── api/                     # API 接口定义
├── components/              # 公共组件
│   ├── DateQuery/           # 日期查询组件
│   └── Picker/              # 选择器组件
├── composables/             # 组合式函数
├── constants/               # 常量定义
├── enums/                   # 枚举定义
├── http/                    # HTTP 请求相关
│   ├── adapters/            # 请求适配器
│   ├── tools/               # 工具函数
│   └── types.ts             # 类型定义
├── layouts/                 # 布局组件
├── pages/                   # 页面目录
│   ├── index/               # 首页
│   ├── login/               # 登录页
│   ├── work/                # 工作台
│   └── mine/                # 个人中心
├── router/                  # 路由配置
├── store/                   # 状态管理
├── types/                   # TypeScript 类型
├── utils/                   # 工具函数
├── App.vue                  # 应用根组件
├── main.ts                  # 应用入口文件
├── manifest.json            # 应用配置文件
├── pages.json               # 页面路由配置
└── theme.json               # 主题配置
```

## 在线演示

- 📱 移动端：[https://service.fastapiadmin.com/app](https://service.fastapiadmin.com/app)
- 📖 在线文档：[https://service.fastapiadmin.com/](https://service.fastapiadmin.com/)

## 快速开始

### 环境要求

- **Node.js** >= 20
- **pnpm** >= 9

### 安装与运行

```bash
cd frontend/app
pnpm install
pnpm run dev:h5       # 启动 H5 开发服务器
pnpm run build:h5     # 构建 H5 应用
```

### 其他命令

```bash
pnpm run lint:eslint    # ESLint 检查并自动修复
pnpm run lint:prettier  # Prettier 格式化
pnpm run lint:stylelint # Stylelint 检查样式
pnpm run type-check     # TypeScript 类型检查
```

## 截图

| 登录 | 首页 | 个人中心 |
| ---- | ---- | -------- |
| ![移动端登录](../../web/public/app_login.png) | ![移动端首页](../../web/public/app_home.png) | ![移动端个人中心](../../web/public/app_mine.png) |

## 鸣谢

- [uni-app](https://uniapp.dcloud.net.cn/) - 跨平台应用开发框架
- [Vue 3](https://cn.vuejs.org/) - 渐进式 JavaScript 框架
- [Vite](https://cn.vitejs.dev/) - 下一代前端构建工具
- [uni-helper](https://github.com/uni-helper) - 感谢 uni-helper 团队为 uni-app 开发体验优化做出的贡献。
- [vitesse-uni-app](https://github.com/uni-helper/vitesse-uni-app) - 感谢 vitesse-uni-app 提供的快速起手项目。
- [uni-ku](https://uni-ku.js.org/) - 感谢 uni-ku 团队为 uni-app 插件生态做出的贡献。
- [wot-ui-intellisense](https://github.com/wot-ui/wot-ui-intellisense) - wot-ui vscode 代码提示插件
- [awesome-uni-app](https://github.com/uni-helper/awesome-uni-app) - 多端统一开发框架 uni-app 优秀开发资源汇总
- [create-uni](https://github.com/uni-helper/create-uni) - 快速创建 uni-app 项目
- [wot-starter-retail](https://github.com/Moonofweisheng/wot-starter-retail) - 基于 wot-ui 的 uni-app 零售行业模板
- [uni-mini-ci](https://github.com/Moonofweisheng/uni-mini-ci) - 一个 uni-app 小程序端构建后支持 CI（持续集成）的插件
- [@wot-ui/router](https://github.com/wot-ui/my-uni) - 一个基于 vue3 和 Typescript 的轻量级 uni-app 路由库
- [uni-ku-root](https://github.com/uni-ku/root) - 一个模拟 App.vue 原有能力的根组件插件
- [uni-echarts](https://uni-echarts.xiaohe.ink/) - 适用于 uni-app 的 Apache ECharts 组件

## 许可证

本项目采用 [MIT](LICENSE) 许可证。

[![Star History Chart](https://api.star-history.com/svg?repos=FastapiAdmin/FastapiAdmin&type=Date)](https://star-history.com/#FastapiAdmin/FastapiAdmin&Date)

---

**如果这个项目对你有帮助，请给一个 ⭐ Star**

Made with ❤️ by FastApp Team

## wot-UI 组件库

基础组件：
  wd-button 按钮
  wd-icon 图标
  wd-text 文本
  Layout 布局：wd-row、wd-col提供了 24列 栅格，通过在 wd-col 上设置 span 属性，通过计算当前内容所占百分比进行分栏
  wd-cell-group、wd-cell 单元格
  wd-fab 悬浮按钮
  wd-transition 过渡动画
  wd-resize 监听元素尺寸变化
  wd-config-provider 组件Wot全局配置
  wd-root-portal 根节点传送，是否从页面中脱离出来，用于解决各种 fixed 失效问题，主要用于制作弹窗、弹出层等。
导航类组件：
  wd-navbar 导航栏
  wd-tabbar、wd-tabbar-item 标签栏
  wd-tabs 标签页
  wd-segmented 分段控制器
  wd-sidebar、wd-sidebar-item 侧边栏
  wd-pagination 分页组件
  wd-index-bar、wd-index-anchor  索引栏
  wd-backtop 回到顶部
录入类组件：
  wd-form、wd-form-item 表单
  wd-input 输入框
  wd-textarea 文本域
  wd-password-input 密码输入框
  wd-keyboard 键盘输入框
  wd-input-number 数字输入框
  wd-search 搜索框
  wd-checkbox-group、wd-checkbox 复选框
  wd-radio-group、wd-radio 单选框
  wd-switch 开关按钮
  wd-rate 评分
  wd-slider 滑块
  wd-picker 选择器
  wd-picker-view 选择器视图
  wd-select-picker 单复选选择器
  wd-cascader 级联选择器
  wd-calendar 日历选择器
  wd-calendar-view 日历面板
  wd-datetime-picker 日期时间选择器
  wd-upload 图片、视频和文件上传组件
  wd-signature 签名组件
  wd-slide-verify 滑动验证组件
反馈组件：
  wd-popup 弹出层，用于展示弹窗、信息提示等内容。
  wd-overlay 遮罩层，用于在弹出层显示时，遮挡背景，防止用户操作。
  wd-dialog 弹出对话框，常用于消息提示、操作确认和输入收集，支持函数式调用
  wd-action-sheet 操作表单，从底部弹出的动作菜单面板
  wd-drop-menu wd-drop-menu-item 下拉菜单
  wd-popover 气泡，常用于展示提示信息或菜单操作
  wd-tooltip 文字提示，用于展示简短提示信息，支持多方向定位、受控显隐、自定义内容和动态更新位置
  wd-floating-panel 浮动在页面底部的面板，用户可以通过上下拖动秒板来浏览内容，常用于地图导航
  wd-loading 加载中组件，用于在异步操作进行中显示加载状态，防止用户操作
  wd-progress 进度条，用于展示任务完成进度
  wd-circle 圆形进度条，用于展示任务完成进度，支持自定义进度条颜色、进度条宽度、进度条高度等
  wd-toast 轻提示，轻提示组件，用于消息通知、加载提示和操作结果反馈，支持组件挂载点配合 useToast() 进行函数式调用。
  wd-notify 消息通知，用于在页面顶部展示通知信息。
  wd-notice-bar 通知栏，用于在页面顶部展示通知信息，支持自定义内容和样式
  wd-swipe-action 滑动操作，用于在列表项上添加滑动操作按钮，支持自定义按钮内容和样式
  wd-sort-button 排序按钮，用于在列表项上添加排序按钮，支持自定义按钮内容和样式
  wd-empty 空状态组件，用于展示无数据或无结果的情况，一般用于兜底占位展示
  wd-count-down 倒计时组件，用于实时展示倒计时数值，支持毫秒级渲染与手动控制
  wd-count-to 数字滚动组件，用于展示数值变化，支持自定义滚动速度、滚动时间等
展示类组件：
  wd-avatar 头像, 用来代表用户或事物，支持图片、文本或图标展示
  wd-badge 徽标，用于展示未读消息、未完成任务等数量，支持自定义数量、颜色、位置等
  wd-tag 标签，用于展示分类、状态、标签等信息，支持自定义标签内容、样式、位置等
  wd-card 卡片，用于展示信息、操作、内容等，支持自定义卡片内容、样式、位置等
  wd-divider 分割线，用于分隔不同内容区域，支持自定义分割线内容、样式、位置等
  wd-gap 间距组件，用于在元素之间添加间距，支持自定义间距大小、方向等
  wd-grid 宫格，用于在页面上创建网格布局，支持自定义网格列数、网格间距等
  wd-collapse、wd-collapse-item 折叠面板，将一组内容放置在多个折叠面板中，点击面板标题可展开或收起内容
  wd-steps、wd-step 步骤条，用于引导用户按照流程完成任务，或向用户展示当前所处的步骤状态
  wd-sticky 粘性组件，用于在页面滚动时保持元素在顶部或底部，不被内容遮挡
  wd-skeleton 骨架屏组件，用于在数据加载中展示占位符，防止用户操作
  wd-loadmore 加载更多组件，用于在列表底部添加加载更多按钮，点击后加载更多数据
  wd-img 增强版图片组件，支持填充模式、懒加载、加载态/失败态插槽，以及点击预览。
  wd-image-preview 图片预览组件，用于在点击图片时预览图片，支持自定义预览位置、预览大小等。
  wd-video-preview 视频预览组件，用于在点击视频时预览视频，支持自定义预览位置、预览大小等。
  wd-img-cropper 图片剪裁组件，用于图片裁剪，支持拖拽、缩放、旋转等操作
  wd-swiper 轮播图组件，用于展示图片、视频等内容，支持自动播放、手动切换、循环播放等
  wd-table wd-table-column 用于展示多条结构类似的数据，支持固定列、排序、合并单元格与虚拟滚动等能力
  wd-watermark 在页面或组件上添加指定的图片或文字，可用于版权保护、品牌宣传等场景
  wd-curtain 幕帘组件，用于在页面上创建一个透明的遮罩层，一般用于公告类图片弹窗展示
组合式api
  useUpload:用于处理文件上传和选择相关的逻辑
  useCountDown:用于处理倒计时相关的逻辑
  useToast:用于处理轻提示相关的逻辑
  useDialog:用于处理弹窗相关的逻辑,useDialog 用于函数式调用 wd-dialog，支持 alert、confirm、prompt、show 和 close
  useImagePreview:用于处理图片预览相关的逻辑,useImagePreview 用于函数式调用 wd-image-preview，支持自定义预览位置、预览大小等。
  useVideoPreview:用于处理视频预览相关的逻辑,useVideoPreview 用于函数式调用 wd-video-preview，支持自定义预览位置、预览大小等。
  useConfigProvider:用于处理全局配置相关的逻辑,useConfigProvider 用于函数式调用 wd-config-provider，支持自定义全局配置项,用于在 JS 逻辑中注入全局配置（如主题变量），解决在微信小程序等环境中，由于组件渲染机制限制（如原生插槽作用域隔离）或使用 root-portal 导致无法获取父级 ConfigProvider 配置的问题。
  提示:需要和 ConfigProvider 组件配合使用，使用 ConfigProvider 组件包裹你的组件。用于解决小程序端依赖注入的限制，导致部分场景下无法获取父级 ConfigProvider 配置的问题。
