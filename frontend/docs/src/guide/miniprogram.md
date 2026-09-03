---
layout: doc
outline: "deep"
title: FastApp 移动端开发指南
description: FastApp 移动端开发指南,基于 UniApp + Vue3 + Wot Design Uni 实现 H5、微信小程序、Android/iOS App 三端统一开发,涵盖环境配置、组件使用、API 接入与发布流程。
---
# FastApp 移动端开发指南

## 📱项目概述

**FastApp** 是 FastApiAdmin 项目的移动端应用，基于 **Uni App** 框架开发，支持一套代码多端运行（包括 H5、微信小程序、支付宝小程序、App 等）。采用 Vue 3 + TypeScript + Vite 等现代化技术栈，集成了完善的代码规范和开发工具链，为开发者提供开箱即用的移动端开发解决方案。

### 核心功能

- **用户认证**：登录、注册、密码重置、权限管理
- **首页展示**：轮播图、快捷导航、通知公告、数据统计
- **工作台**：业务功能入口，支持权限控制
- **个人中心**：个人信息、设置、FAQ、问题反馈
- **数据统计**：实时访客数、浏览量等数据展示
- **主题切换**：支持深色/浅色主题切换

### 系统功能特性

- 🔐 **用户管理** - 支持用户注册、登录、权限管理等功能，提供完善的用户体系
- 📊 **数据统计** - 提供实时数据分析和可视化报表，帮助您更好地了解业务状况
- 📁 **文件管理** - 支持文件上传、下载、分类管理，提供安全的文件存储服务
- 🔔 **消息通知** - 实时消息推送和系统通知，确保您不会错过重要信息
- 🛡️ **权限控制** - 基于RBAC的权限管理模型，灵活控制用户访问权限
- 📝 **日志审计** - 完整的操作日志记录，便于追踪和审计用户行为

## 🛠️技术栈

| 技术 | 版本 | 说明 |
|------|------|------|
| Uni App | 3.0.0+ | 跨平台移动端开发框架 |
| Vue3 | 3.5.22+ | 前端框架（Composition API） |
| TypeScript | 5.9.2+ | 类型系统 |
| Vite | 6.0+ | 构建工具 |
| Pinia | 2.1+ | 状态管理 |
| Wot Design Uni | 1.9.1+ | UI 组件库 |
| UnoCSS | 0.58+ | 原子化 CSS 引擎 |
| VueUse | 10.7+ | Vue Composition API 工具集合 |
| @stomp/stompjs | 7.0+ | WebSocket 消息协议库 |

## 📁项目结构

```
FastApp/
├─ public/             # 静态资源
│  └─ favicon.ico      # 网站图标
├─ src/                # 源代码
│  ├─ api/             # API 接口
│  │  ├─ auth.ts       # 认证相关接口
│  │  ├─ file.ts       # 文件相关接口
│  │  └─ user.ts       # 用户相关接口
│  ├─ components/      # 组件
│  │  ├─ cu-date-query/ # 日期查询组件
│  │  ├─ cu-picker/     # 选择器组件
│  │  ├─ qiun-error/    # 错误提示组件
│  │  └─ qiun-loading/  # 加载组件
│  ├─ composables/     # 组合式函数
│  │  ├─ useNavigationBar.ts # 导航栏管理
│  │  ├─ useStomp.ts   # WebSocket 管理
│  │  └─ useTabbar.ts  # 标签栏管理
│  ├─ constants/       # 常量定义
│  │  ├─ index.ts      # 常量定义
│  │  └─ storage.constant.ts # 存储键名
│  ├─ enums/           # 枚举定义
│  │  ├─ api-code.enum.ts # API 错误码
│  │  └─ api-header.enum.ts # API 头部
│  ├─ layouts/         # 布局组件
│  │  ├─ default.vue   # 默认布局
│  │  └─ tabbar.vue    # 标签栏布局
│  ├─ pages/           # 页面文件
│  │  ├─ index/        # 首页
│  │  │  ├─ data.ts     # 数据定义
│  │  │  ├─ index.vue   # 首页组件
│  │  │  └─ types.ts    # 类型定义
│  │  ├─ login/        # 登录页
│  │  │  └─ index.vue   # 登录组件
│  │  ├─ mine/         # 个人中心
│  │  │  ├─ about/      # 关于页面
│  │  │  ├─ faq/        # FAQ页面
│  │  │  ├─ feedback/   # 反馈页面
│  │  │  ├─ profile/    # 个人资料
│  │  │  ├─ settings/   # 设置页面
│  │  │  └─ index.vue   # 个人中心组件
│  │  └─ work/         # 工作台
│  │     ├─ data.ts     # 数据定义
│  │     ├─ index.vue   # 工作台组件
│  │     └─ types.ts    # 类型定义
│  ├─ router/          # 路由配置
│  │  └─ index.ts      # 路由配置文件
│  ├─ static/          # 静态资源
│  │  ├─ icons/        # 图标
│  │  ├─ images/       # 图片
│  │  └─ logo.svg      # Logo
│  ├─ store/           # 状态管理
│  │  ├─ modules/      # 模块
│  │  │  ├─ theme.store.ts # 主题管理
│  │  │  └─ user.store.ts # 用户管理
│  │  └─ index.ts      # 状态管理配置
│  ├─ styles/          # 样式文件
│  │  └─ index.scss    # 全局样式
│  ├─ types/           # TypeScript 类型定义
│  ├─ utils/           # 工具函数
│  │  ├─ auth.ts       # 认证工具
│  │  ├─ color.ts      # 颜色工具
│  │  ├─ index.ts      # 工具函数
│  │  ├─ request.ts    # 请求工具
│  │  └─ storage.ts    # 存储工具
│  ├─ App.vue          # 应用根组件
│  ├─ main.ts          # 应用入口文件
│  ├─ manifest.json    # 应用配置文件
│  ├─ pages.json       # 页面路由配置
│  └─ theme.json       # 主题配置
├─ .env.development    # 开发环境配置
├─ .env.production     # 生产环境配置
├─ package.json        # 项目依赖
├─ pages.config.ts     # 页面配置
├─ tsconfig.json       # TypeScript 配置
├─ unocss.config.ts    # UnoCSS 配置
└─ vite.config.ts      # Vite 配置
```

## 🔧环境搭建

### 1. 环境要求

- **Node.js** >= 22
- **pnpm** >= 9

### 2. 安装依赖

```sh
# 进入项目目录
cd FastApp

# 安装项目依赖
pnpm install
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件配置环境变量：

```bash
# API 基础地址
VITE_API_BASE_URL=http://localhost:8001

# API 前缀
VITE_APP_BASE_API=/api

# 开发服务器端口
VITE_APP_PORT=5180
```

## 🚀开发流程

### 1. 启动开发服务器

#### H5 开发

```sh
# 启动 H5 开发服务器
pnpm run dev:h5

# 访问地址
# http://localhost:5180/app
```

#### 微信小程序开发

```sh
# 启动微信小程序开发服务器
pnpm run dev:mp-weixin

# 在微信开发者工具中导入项目目录：FastApp/dist/dev/mp-weixin
```

#### 其他平台开发

```sh
# 启动支付宝小程序开发服务器
pnpm run dev:mp-alipay

# 启动百度小程序开发服务器
pnpm run dev:mp-baidu

# 启动字节跳动小程序开发服务器
pnpm run dev:mp-toutiao

# 启动 QQ 小程序开发服务器
pnpm run dev:mp-qq
```

## 📚页面开发

### 1. 创建新页面

1. **在 `pages.json` 中添加页面配置**：

```json
{
  "pages": [
    {
      "path": "pages/index/index",
      "style": {
        "navigationBarTitleText": "首页"
      }
    },
    // 其他页面...
  ]
}
```

2. **创建页面文件**：

```
FastApp/src/pages/
└─ new-page/
   ├─ index.vue      # 页面组件
   ├─ data.ts        # 数据定义（可选）
   └─ types.ts       # 类型定义（可选）
```

3. **页面示例**：

```vue
<template>
  <view class="page">
    <view class="title">新页面</view>
    <view class="content">
      <text>{{ message }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const message = ref('Hello FastApp!');
</script>

<style scoped>
.page {
  padding: 20rpx;
}

.title {
  font-size: 32rpx;
  font-weight: bold;
  margin-bottom: 20rpx;
}

.content {
  font-size: 28rpx;
  color: #666;
}
</style>
```

### 2. 路由管理

#### 页面跳转

```typescript
// 普通跳转
uni.navigateTo({
  url: '/pages/new-page/index'
});

// 带参数跳转
uni.navigateTo({
  url: '/pages/new-page/index?id=1&name=test'
});

// 重定向跳转
uni.redirectTo({
  url: '/pages/new-page/index'
});

// 跳转到 tabBar 页面
uni.switchTab({
  url: '/pages/index/index'
});

// 关闭所有页面，打开新页面
uni.reLaunch({
  url: '/pages/new-page/index'
});
```

#### 接收参数

```typescript
// 在页面 onLoad 生命周期中接收参数
import { onLoad } from '@dcloudio/uni-app';

onLoad((options) => {
  console.log('参数：', options);
  // options.id, options.name
});
```

## 📡API 调用

### 1. 封装的 API 工具

FastApp 使用封装的 `request.ts` 工具进行 API 调用，支持自动添加认证 token、错误处理等功能。

### 2. API 接口定义

API 接口定义在 `src/api` 目录下，按模块分类：

```typescript
// src/api/user.ts 示例
import request from '../utils/request';

export const userApi = {
  // 获取用户信息
  getUserInfo: () => {
    return request({
      url: '/api/v1/user/info',
      method: 'GET'
    });
  },
  
  // 更新用户信息
  updateUserInfo: (data: any) => {
    return request({
      url: '/api/v1/user/update',
      method: 'POST',
      data
    });
  }
};
```

### 3. 调用 API

```typescript
import { userApi } from '../api/user';

// 调用 API
const getUserInfo = async () => {
  try {
    const res = await userApi.getUserInfo();
    console.log('用户信息：', res.data);
  } catch (error) {
    console.error('获取用户信息失败：', error);
  }
};

// 调用更新用户信息 API
const updateUser = async () => {
  try {
    const res = await userApi.updateUserInfo({
      name: '新名字',
      avatar: '新头像'
    });
    console.log('更新成功：', res.data);
  } catch (error) {
    console.error('更新失败：', error);
  }
};
```

### 4. WebSocket 实时通信

FastApp 集成了 `@stomp/stompjs` 库，支持 WebSocket 实时通信，通过封装的 `useStomp` 组合式函数可以方便地使用：

```typescript
// 使用 WebSocket
import { useStomp } from '../composables/useStomp';

const {
  connect,
  disconnect,
  subscribe,
  send,
  isConnected
} = useStomp();

// 连接 WebSocket
const initWebSocket = () => {
  connect({
    url: 'ws://localhost:8001/ws',
    onConnect: () => {
      console.log('WebSocket 连接成功');
      // 订阅消息
      subscribe('/topic/messages', (message) => {
        console.log('收到消息：', message);
      });
    },
    onError: (error) => {
      console.error('WebSocket 连接失败：', error);
    }
  });
};

// 发送消息
const sendMessage = () => {
  if (isConnected.value) {
    send('/app/message', {
      content: 'Hello WebSocket!'
    });
  }
};

// 断开连接
const closeWebSocket = () => {
  disconnect();
};
```

## 🔐认证管理

### 1. 登录流程

```typescript
import { authApi } from '../api/auth';
import { useUserStore } from '../store/modules/user.store';

const userStore = useUserStore();

const login = async (username: string, password: string) => {
  try {
    const res = await authApi.login({
      username,
      password
    });
    
    // 保存 token
    userStore.setToken(res.data.token);
    
    // 获取用户信息
    await userStore.getUserInfo();
    
    // 跳转到首页
    uni.switchTab({ url: '/pages/index/index' });
  } catch (error) {
    console.error('登录失败：', error);
  }
};
```

### 2. 登出流程

```typescript
import { useUserStore } from '../store/modules/user.store';

const userStore = useUserStore();

const logout = () => {
  // 清除 token 和用户信息
  userStore.logout();
  
  // 跳转到登录页
  uni.redirectTo({ url: '/pages/login/index' });
};
```

### 3. 权限控制

可以使用全局路由守卫或页面级权限检查来实现权限控制：

```typescript
// 在页面 onLoad 中检查权限
import { onLoad } from '@dcloudio/uni-app';
import { useUserStore } from '../store/modules/user.store';

const userStore = useUserStore();

onLoad(() => {
  // 检查是否登录
  if (!userStore.token) {
    uni.redirectTo({ url: '/pages/login/index' });
    return;
  }
  
  // 检查用户权限
  if (!userStore.hasPermission('required_permission')) {
    uni.showToast({
      title: '权限不足',
      icon: 'none'
    });
    uni.navigateBack();
  }
});
```

## 🎨UI 组件

### 1. 使用 Wot Design Uni

FastApp 使用 **Wot Design Uni** 作为 UI 组件库，提供了丰富的移动端组件：

```vue
<template>
  <view class="page">
    <!-- 按钮 -->
    <wd-button type="primary" @click="handleClick">主要按钮</wd-button>
    
    <!-- 输入框 -->
    <wd-input v-model="value" placeholder="请输入内容" />
    
    <!-- 列表 -->
    <wd-list>
      <wd-list-item title="标题" value="值" />
      <wd-list-item title="标题2" value="值2" />
    </wd-list>
    
    <!-- 弹窗 -->
    <wd-popup v-model:visible="popupVisible" title="弹窗标题">
      <view>弹窗内容</view>
    </wd-popup>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue';

const value = ref('');
const popupVisible = ref(false);

const handleClick = () => {
  popupVisible.value = true;
};
</script>
```

### 2. 使用 UnoCSS

FastApp 集成了 UnoCSS 原子化 CSS 引擎，支持类名方式快速开发：

```vue
<template>
  <view class="flex flex-col items-center p-4">
    <view class="text-xl font-bold mb-4">Hello FastApp</view>
    <view class="w-full max-w-md bg-white rounded-lg shadow-md p-4">
      <view class="text-gray-700">Welcome to FastApp</view>
    </view>
  </view>
</template>
```

### 3. 自定义组件

可以在 `src/components` 目录下创建自定义组件：

```vue
<!-- src/components/custom-button.vue -->
<template>
  <view class="custom-button" @click="$emit('click')">
    <slot></slot>
  </view>
</template>

<script setup lang="ts">
defineEmits(['click']);
</script>

<style scoped>
.custom-button {
  padding: 12rpx 24rpx;
  background-color: #007aff;
  color: #fff;
  border-radius: 8rpx;
  text-align: center;
}
</style>
```

## 📱多平台适配

### 1. 条件编译

使用 Uni App 的条件编译语法，可以为不同平台编写不同的代码：

```vue
<template>
  <view>
    <!-- #ifdef H5 -->
    <view>这是 H5 平台的内容</view>
    <!-- #endif -->
    
    <!-- #ifdef MP-WEIXIN -->
    <view>这是微信小程序平台的内容</view>
    <!-- #endif -->
    
    <!-- #ifdef APP-PLUS -->
    <view>这是 App 平台的内容</view>
    <!-- #endif -->
  </view>
</template>

<script setup lang="ts">
// #ifdef H5
console.log('H5 平台');
// #endif

// #ifdef MP-WEIXIN
console.log('微信小程序平台');
// #endif
</script>

<style scoped>
/* #ifdef H5 */
.view {
  font-size: 16px;
}
/* #endif */

/* #ifdef MP-WEIXIN */
.view {
  font-size: 28rpx;
}
/* #endif */
</style>
```

### 2. 平台特有 API

使用平台特有 API 时，需要注意添加条件编译：

```typescript
// 调用微信小程序特有 API
// #ifdef MP-WEIXIN
wx.getLocation({
  type: 'wgs84',
  success: (res) => {
    console.log('位置信息：', res);
  }
});
// #endif

// 调用 App 特有 API
// #ifdef APP-PLUS
plus.device.getInfo({
  success: (info) => {
    console.log('设备信息：', info);
  }
});
// #endif
```

## 🚀性能优化

### 1. 代码优化

- **减少页面层级**：尽量减少页面嵌套层级，最多不超过 5 层
- **按需加载**：使用分包加载、组件按需导入等方式减少初始包大小
- **避免频繁更新**：使用 `nextTick` 合并更新，避免频繁触发渲染
- **使用虚拟列表**：长列表使用虚拟列表，避免一次性渲染过多数据

### 2. 网络优化

- **缓存数据**：使用本地存储缓存不常变化的数据
- **请求合并**：合并多个请求，减少网络请求次数
- **延迟加载**：非关键资源延迟加载
- **使用 WebSocket**：实时数据使用 WebSocket，减少轮询

### 3. 存储优化

- **合理使用本地存储**：根据数据类型选择合适的存储方式（localStorage、sessionStorage、IndexedDB）
- **清理过期数据**：定期清理过期或无用的数据
- **加密敏感数据**：敏感数据（如 token）进行加密存储

## 📦打包发布

### 1. 构建生产版本

#### H5 构建

```bash
pnpm run build:h5

# 构建产物在 dist/build/h5 目录
```

#### 微信小程序构建

```bash
pnpm run build:mp-weixin

# 构建产物在 dist/build/mp-weixin 目录
```

#### 其他平台构建

```bash
# 构建支付宝小程序
pnpm run build:mp-alipay

# 构建百度小程序
pnpm run build:mp-baidu

# 构建字节跳动小程序
pnpm run build:mp-toutiao

# 构建 QQ 小程序
pnpm run build:mp-qq
```

### 2. 发布流程

#### H5 部署

1. 执行构建命令：`pnpm run build:h5`
2. 将 `dist/build/h5` 目录部署到 Web 服务器
3. 配置服务器支持 SPA 路由（如 Nginx 的 `try_files`）

#### 小程序发布

1. 执行对应平台的构建命令
2. 使用对应平台的开发者工具打开构建产物目录
3. 在开发者工具中上传代码并提交审核

#### App 打包

1. 使用 HBuilderX 打开项目
2. 配置 App 相关信息（图标、启动页等）
3. 选择云打包或本地打包
4. 下载安装包并发布到应用商店

## 🐛常见问题及解决方案

### 1. 开发环境问题

**问题**：H5 开发时跨域错误
**解决方案**：在 `vite.config.ts` 中配置代理：

```typescript
// vite.config.ts
proxy: {
  [env.VITE_APP_BASE_API]: {
    changeOrigin: true,
    target: env.VITE_API_BASE_URL,
  },
}
```

**问题**：微信小程序开发时 API 请求失败
**解决方案**：在微信公众平台设置合法域名，或在开发者工具中开启「不校验合法域名」选项。

### 2. 运行时问题

**问题**：页面白屏
**解决方案**：检查是否有语法错误、API 调用错误，查看控制台日志。

**问题**：数据加载失败
**解决方案**：检查网络连接，API 地址是否正确，后端服务是否正常。

**问题**：样式错乱
**解决方案**：检查样式代码，使用条件编译适配不同平台。

### 3. 发布问题

**问题**：微信小程序审核失败
**解决方案**：根据审核反馈修改代码，确保符合微信小程序规范。

**问题**：包大小超过限制
**解决方案**：使用分包加载、按需导入组件、压缩资源等方式减少包大小。

## 📚代码规范

项目集成了完善的代码规范工具：

```bash
# ESLint 检查并自动修复
pnpm run lint:eslint

# Prettier 格式化
pnpm run lint:prettier

# Stylelint 检查样式
pnpm run lint:stylelint

# TypeScript 类型检查
pnpm run type-check
```

## 📚自动导入

项目配置了自动导入，以下内容无需手动导入：

- Vue 3 API（`ref`, `computed`, `watch` 等）
- uni-app API（`uni.request`, `uni.navigateTo` 等）
- Pinia（`defineStore`, `storeToRefs` 等）
- 路由（`useRouter`, `useRoute` 等）
- 组件库工具（`useToast`, `useMessage` 等）
- `src/composables` 目录下的组合式函数
- `src/utils` 目录下的工具函数
- `src/api` 目录下的 API 函数

## 📚参考文档

- **Uni App 官方文档**：[https://uniapp.dcloud.io/](https://uniapp.dcloud.io/)
- **Wot Design Uni 文档**：[https://wot-design-uni.webapp.plus/](https://wot-design-uni.webapp.plus/)
- **Vue3 官方文档**：[https://cn.vuejs.org/](https://cn.vuejs.org/)
- **TypeScript 官方文档**：[https://www.typescriptlang.org/](https://www.typescriptlang.org/)
- **微信小程序开发文档**：[https://developers.weixin.qq.com/miniprogram/dev/framework/](https://developers.weixin.qq.com/miniprogram/dev/framework/)

## 🤝贡献指南

欢迎为 FastApp 项目贡献代码！请遵循以下步骤：

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄许可协议

FastApp 项目采用 MIT 许可协议，详见 [LICENSE](https://github.com/fastapiadmin/FastApp/blob/master/LICENSE) 文件。
