<template>
  <ElConfigProvider
    :size="size"
    :locale="locale"
    :z-index="3000"
    :card="{
      shadow: 'never',
    }"
  >
    <ElWatermark
      :font="{ color: fontColor }"
      :content="showWatermark ? watermarkContent : ''"
      :z-index="9999"
      class="wh-full"
    >
      <RouterView></RouterView>

      <!-- AI 助手 -->
      <AiAssistant v-if="enableAiAssistant" />
    </ElWatermark>
  </ElConfigProvider>
</template>

<script setup lang="ts">
import { computed, onBeforeMount, onMounted, onUnmounted, watch } from "vue";
import { useWindowSize } from "@vueuse/core";
import { useAppStore, useUserStore } from "./store";
import { useSettingsStore } from "./store/modules/setting.store";
import { defaultSettings } from "./config/setting";
import { ComponentSize } from "./enums/settings/layout.enum";
import { MOBILE_BREAKPOINT } from "./utils/constants/definitions";
import AiAssistant from "./components/others/fa-ai-assistant/index.vue";
import { hexToRgba, toggleTransition } from "./utils/ui";
import { initializeTheme } from "./hooks/core/useTheme";
import { useAppBootstrap } from "@/hooks/core/useAppBootstrap";
import { useEventBus } from "@/hooks/core/useEventBus";
import { ThemeMode } from "./enums";
import en from "element-plus/es/locale/lang/en";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { router } from "@/router";
import { ElNotification } from "element-plus";

const appStore = useAppStore();
const settingsStore = useSettingsStore();
const userStore = useUserStore();
const { width } = useWindowSize();

// SSE 事件总线
const { connect, disconnect, subscribe } = useEventBus();

// H5 用小尺寸，桌面用用户设置的大小
const size = computed(() => {
  if (width.value < MOBILE_BREAKPOINT) return "small" as ComponentSize;
  return appStore.size as ComponentSize;
});
const showWatermark = computed(() => settingsStore.showWatermark);
const watermarkContent = defaultSettings.watermarkContent;

// 根据语言设置返回对应的语言包
const locale = computed(() => {
  return appStore.language === "en" ? en : zhCn;
});

// 只有在启用 AI 助手且用户已登录时才显示
const enableAiAssistant = computed(() => {
  const isEnabled = settingsStore.userEnableAi;
  const isLoggedIn = userStore.basicInfo && Object.keys(userStore.basicInfo).length > 0;
  return isEnabled && isLoggedIn;
});

// 水印文字默认使用当前主题色（半透明），随主题色设置变化
const fontColor = computed(() => {
  const hex = settingsStore.themeColor || defaultSettings.themeColor;
  const alpha = settingsStore.theme === ThemeMode.DARK ? 0.22 : 0.16;
  try {
    return hexToRgba(hex, alpha).rgba;
  } catch {
    return hexToRgba(defaultSettings.themeColor, alpha).rgba;
  }
});

/**
 * 应用根组件生命周期：
 *
 * onBeforeMount
 *   1. toggleTransition(true)  —— 临时禁用页面过渡，避免主题切换时的闪烁
 *   2. initializeTheme()       —— 加载主题配色(CSS 变量)、暗色模式 class、auto 监听
 *
 * onMounted
 *   1. bootstrap()                                —— 存储检查 → 过渡恢复 → 版本升级 → 站点配置
 *   2. 监听 "app:storage-invalidated" 事件        —— 存储异常时由 storage 模块派发
 */
onBeforeMount(() => {
  toggleTransition(true);
  initializeTheme();
});

// 存储失效时跳转登录页（由 storage 模块 detect 到异常后派发）
const handleStorageInvalidated = () => {
  router.push({ name: "Login" });
};

const { bootstrap } = useAppBootstrap();

onMounted(() => {
  bootstrap();

  // 存储检测到异常并已清除数据 → 由路由守卫完成登出清理
  window.addEventListener("app:storage-invalidated", handleStorageInvalidated);

  // 全局网络状态监听
  window.addEventListener("offline", () => {
    ElNotification({
      title: "网络已断开",
      message: "请检查您的网络连接",
      type: "error",
      duration: 0,
    });
  });
  window.addEventListener("online", () => {
    ElMessage.success("网络已恢复");
  });

  // 用户登录后连接 SSE
  watch(
    () => userStore.basicInfo,
    (info) => {
      if (info && Object.keys(info).length > 0) {
        connect();
        subscribe("payment_success", (data) => {
          ElNotification({
            title: "支付成功",
            message: `订单 ${data.order_no} 已支付成功`,
            type: "success",
            duration: 5000,
          });
        });
        subscribe("ticket_reply", (data) => {
          ElNotification({
            title: "工单回复",
            message: `"${data.title}" 有了新回复`,
            type: "info",
            duration: 5000,
          });
        });
      } else {
        disconnect();
      }
    },
    { immediate: true }
  );
});

onUnmounted(() => {
  window.removeEventListener("app:storage-invalidated", handleStorageInvalidated);
  disconnect();
});
</script>
