/**
 * useEventBus — SSE 事件总线
 *
 * 通过 EventSource 连接服务端 SS E 端点，接收实时推送事件。
 * 连接建立后自动监听心跳，断线自动重连。
 *
 * ## 使用示例
 *
 * ```typescript
 * const { isConnected, subscribe } = useEventBus()
 *
 * // 监听支付成功事件
 * subscribe('payment_success', (data) => {
 *   ElNotification({ title: '支付成功', message: `订单 ${data.order_no} 已支付`, type: 'success' })
 * })
 *
 * // 监听工单回复
 * subscribe('ticket_reply', (data) => {
 *   ElNotification({ title: '工单回复', message: data.title, type: 'info' })
 * })
 * ```
 *
 * @module useEventBus
 */

import { ref, onUnmounted } from "vue";
import { Auth } from "@utils";

/** SSE 事件回调 */
type EventCallback = (data: Record<string, any>) => void;

/** 连接状态 */
export type ConnectionState = "connecting" | "connected" | "disconnected";

export function useEventBus() {
  const isConnected = ref<ConnectionState>("disconnected");
  const eventSource = ref<EventSource | null>(null);
  const listeners = new Map<string, Set<EventCallback>>();
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  const MAX_RECONNECT_DELAY = 30000; // 最大重连间隔 30s

  /** 获取 SSE 端点 URL */
  function getSSEUrl(): string {
    const token = Auth.getAccessToken();
    const baseURL = import.meta.env.VITE_APP_BASE_API || "";
    return `${baseURL}/common/sse/events?token=${encodeURIComponent(token)}`;
  }

  /** 建立 SSE 连接 */
  function connect() {
    // 关闭旧连接
    disconnect();

    const url = getSSEUrl();
    if (!url) return;

    isConnected.value = "connecting";

    try {
      const es = new EventSource(url, { withCredentials: true });

      es.onopen = () => {
        isConnected.value = "connected";
        reconnectAttempts = 0;
      };

      es.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);

          // 心跳事件忽略
          if (data.type === "heartbeat") return;

          // 分发到对应事件类型的回调
          const typeListeners = listeners.get(data.type);
          if (typeListeners) {
            typeListeners.forEach((cb) => cb(data));
          }

          // 同时触发 '*' 通配监听（所有事件）
          const allListeners = listeners.get("*");
          if (allListeners) {
            allListeners.forEach((cb) => cb(data));
          }
        } catch {
          // JSON 解析失败，静默忽略
        }
      };

      es.onerror = () => {
        isConnected.value = "disconnected";
        es.close();
        scheduleReconnect();
      };

      eventSource.value = es;
    } catch {
      isConnected.value = "disconnected";
      scheduleReconnect();
    }
  }

  /** 断开 SSE 连接 */
  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (eventSource.value) {
      eventSource.value.close();
      eventSource.value = null;
    }
    isConnected.value = "disconnected";
  }

  /** 指数退避重连 */
  function scheduleReconnect() {
    if (reconnectTimer) return;

    reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts - 1), MAX_RECONNECT_DELAY);

    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  /**
   * 订阅事件
   * @param type 事件类型，'*' 表示所有事件
   * @param callback 事件回调
   */
  function subscribe(type: string, callback: EventCallback) {
    if (!listeners.has(type)) {
      listeners.set(type, new Set());
    }
    listeners.get(type)!.add(callback);

    // 返回取消订阅函数
    return () => {
      listeners.get(type)?.delete(callback);
    };
  }

  // 组件卸载时自动断开
  onUnmounted(() => {
    disconnect();
  });

  return {
    isConnected,
    connect,
    disconnect,
    subscribe,
    eventSource,
  };
}
