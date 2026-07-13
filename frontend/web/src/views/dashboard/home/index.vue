<template>
  <div class="flex flex-col relative last:mb-0">
    <FaDashboardSkeleton v-if="loading" />
    <template v-else>
      <!-- 租户模式：状态横幅 -->
      <div v-if="isTenantMode && workspace" class="mb-5">
        <FaBasicBanner
          :title="`${workspace.tenant.name}`"
          :subtitle="`${workspace.package?.name || '暂无套餐'} · 剩余 ${workspace.tenant.days_remaining} 天 · ${workspace.tenant.status_label}`"
          :boxStyle="tenantStatusStyle"
          titleColor="var(--fa-gray-900)"
          subtitleColor="var(--fa-gray-500)"
          :decoration="false"
        />
      </div>

      <!-- 租户模式：配额预警提示 -->
      <div v-if="isTenantMode && workspace && quotaWarning" class="mb-5">
        <ElAlert type="warning" :title="quotaWarning" show-icon :closable="false" />
      </div>

      <!-- 左列：主内容区 | 右列：侧边栏 -->
      <ElRow :gutter="20">
        <ElCol :xs="24" :md="18">
          <Banner v-if="!isTenantMode" class="mb-5" />

          <ElRow :gutter="20">
            <ElCol :xs="24" :md="16">
              <ElRow :gutter="20">
                <ElCol :xs="24" :sm="24" :md="24">
                  <CardList />
                </ElCol>
              </ElRow>
              <ElRow :gutter="20" v-if="isTenantMode && workspace">
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaStatsCard
                    icon="ri:user-line"
                    :iconStyle="
                      workspace.quota.usage_percent.users >= 80 ? 'bg-warning' : 'bg-theme'
                    "
                    :boxStyle="
                      workspace.quota.usage_percent.users >= 80 ? 'bg-warning/10!' : 'bg-theme/10!'
                    "
                    title="用户"
                    :description="`上限 ${workspace.quota.max_users || '—'}`"
                    :count="workspace.quota.current_users"
                    :textColor="
                      workspace.quota.usage_percent.users >= 80 ? '#e6a23c' : 'var(--theme-color)'
                    "
                    :showArrow="false"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaStatsCard
                    icon="ri:shield-user-line"
                    :iconStyle="
                      workspace.quota.usage_percent.roles >= 80 ? 'bg-warning' : 'bg-success'
                    "
                    :boxStyle="
                      workspace.quota.usage_percent.roles >= 80
                        ? 'bg-warning/10!'
                        : 'bg-success/10!'
                    "
                    title="角色"
                    :description="`上限 ${workspace.quota.max_roles || '—'}`"
                    :count="workspace.quota.current_roles"
                    :textColor="
                      workspace.quota.usage_percent.roles >= 80
                        ? '#e6a23c'
                        : 'var(--el-color-success)'
                    "
                    :showArrow="false"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaStatsCard
                    icon="ri:organization-chart"
                    :iconStyle="
                      workspace.quota.usage_percent.depts >= 80 ? 'bg-warning' : 'bg-info'
                    "
                    :boxStyle="
                      workspace.quota.usage_percent.depts >= 80 ? 'bg-warning/10!' : 'bg-info/10!'
                    "
                    title="部门"
                    :description="`上限 ${workspace.quota.max_depts || '—'}`"
                    :count="workspace.quota.current_depts"
                    :textColor="
                      workspace.quota.usage_percent.depts >= 80 ? '#e6a23c' : 'var(--el-color-info)'
                    "
                    :showArrow="false"
                  />
                </ElCol>
              </ElRow>
              <ElRow :gutter="20" v-if="isTenantMode && workspace">
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaProgressCard
                    :percentage="workspace.quota.usage_percent.users"
                    title="用户用量"
                    :color="getQuotaColor(workspace.quota.usage_percent.users)"
                    icon="ri:user-line"
                    iconStyle="bg-theme/12 text-theme"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaProgressCard
                    :percentage="workspace.quota.usage_percent.roles"
                    title="角色用量"
                    :color="getQuotaColor(workspace.quota.usage_percent.roles)"
                    icon="ri:shield-user-line"
                    iconStyle="bg-success/12 text-success"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaProgressCard
                    :percentage="workspace.quota.usage_percent.depts"
                    title="部门用量"
                    :color="getQuotaColor(workspace.quota.usage_percent.depts)"
                    icon="ri:organization-chart"
                    iconStyle="bg-info/12 text-info"
                  />
                </ElCol>
              </ElRow>
              <ElRow :gutter="20" v-else>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaStatsCard
                    :icon="'ri:money-cny-box-line'"
                    :iconStyle="'bg-theme'"
                    :boxStyle="'bg-theme/10!'"
                    :title="'总收入'"
                    :description="'月收入超过¥350,000+'"
                    :count="35000"
                    :textColor="'var(--theme-color)'"
                    :decimals="0"
                    :showArrow="false"
                    separator=","
                    customIconStyle="'text-theme! text-3xl!''"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaProgressCard
                    :percentage="65"
                    :title="'任务进度'"
                    :color="'var(--theme-color)'"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaProgressCard
                    :percentage="80"
                    :title="'任务进度'"
                    :color="'var(--theme-color)'"
                    :icon="'ri:twitch-line'"
                    :iconStyle="'bg-theme/12 text-theme'"
                  />
                </ElCol>
              </ElRow>
              <ElRow :gutter="20">
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaBarChartCard
                    :isMiniChart="true"
                    :value="15480"
                    label="浏览量"
                    date="过去14天"
                    :percentage="-4.15"
                    :height="9.5"
                    barWidth="45%"
                    :chartData="[120, 100, 150, 140, 90, 120, 130]"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaLineChartCard
                    :isMiniChart="true"
                    :value="2545"
                    label="粉丝数"
                    date="过去30天"
                    :percentage="1.2"
                    :height="9.5"
                    :showAreaColor="true"
                    :chartData="[150, 180, 160, 200, 180, 220, 240]"
                  />
                </ElCol>
                <ElCol :xs="24" :sm="8" :md="8" class="mb-5">
                  <FaDonutChartCard
                    :value="36358"
                    title="粉丝量"
                    :percentage="18"
                    percentageLabel="较去年"
                    :data="[50, 40]"
                    :height="9.5"
                    currentValue="2022"
                    previousValue="2021"
                    :radius="['50%', '70%']"
                  />
                </ElCol>
              </ElRow>
            </ElCol>
            <ElCol :xs="24" :md="8" class="mb-5">
              <FaTimelineListCard :list="timelineData" title="最近交易" subtitle="2024年12月20日" />
            </ElCol>
          </ElRow>

          <ElRow :gutter="20">
            <ElCol :xs="24" :sm="12" :md="12" class="mb-5">
              <ElCard
                shadow="hover"
                class="overflow-hidden border border-(--el-border-color-lighter) rounded-xl flex flex-col h-full"
              >
                <template #header>
                  <div class="flex flex-wrap gap-3 items-start justify-between w-full">
                    <div>
                      <span
                        class="text-base font-semibold tracking-[0.02em]"
                        style="color: var(--el-text-color-primary)"
                        >日程日历</span
                      >
                      <p
                        class="mt-0.5 text-xs font-normal leading-[1.45]"
                        style="color: var(--el-text-color-secondary)"
                      >
                        点击日期添加或编辑（本地演示）
                      </p>
                    </div>
                  </div>
                </template>
                <div>
                  <FaCalendar />
                </div>
              </ElCard>
            </ElCol>
            <ElCol :xs="24" :sm="12" :md="12" class="mb-5">
              <NewUser />
            </ElCol>
          </ElRow>
        </ElCol>

        <ElCol :xs="24" :md="6" class="flex flex-col gap-5">
          <QuickLinks class="mb-5" />
          <FaDataListCard
            class="mb-5"
            :maxCount="4"
            :list="healthList"
            title="系统健康"
            subtitle="实时 · 30s"
            :showMoreButton="true"
            @more="handleMore"
          />
          <TodoList class="mb-5" />
        </ElCol>
      </ElRow>

      <ElRow :gutter="20">
        <ElCol :xs="24" :sm="6" :md="5" class="mb-5">
          <FaImageCard
            :imageUrl="imageCards.imageUrl"
            :title="imageCards.title"
            :category="imageCards.category"
            :readTime="imageCards.readTime"
            :views="imageCards.views"
            :comments="imageCards.comments"
            :date="imageCards.date"
            @click="handleImageCardClick"
          />
        </ElCol>
        <ElCol :xs="24" :sm="6" :md="5" class="mb-5">
          <FaCardBanner
            :image="bannerIcon4"
            title="版本更新提醒"
            description="FastapiAdmin v3.0.0 已发布，包含优化和新功能。"
            :button="{
              show: true,
              text: '立即更新',
              color: 'var(--theme-color)',
              textColor: '#fff',
            }"
            :cancelButton="{ show: true, text: '稍后提醒', color: '#eee', textColor: '#333' }"
            @click="handleBannerDemoConfirm"
            @cancel="handleBannerDemoCancel"
          />
        </ElCol>
        <ElCol :xs="24" :sm="12" :md="14" class="mb-5">
          <AboutProject />
        </ElCol>
      </ElRow>
    </template>
  </div>
</template>

<script setup lang="ts">
defineOptions({ name: "Home", inheritAttrs: false });

import { ref, computed, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import { useUserStore } from "@stores";
import TenantAPI from "@/api/module_platform/tenant";
import DashboardAPI from "@/api/module_monitor/dashboard";
import type { WorkspaceData } from "@/api/module_platform/tenant";
import type { DashboardStats, RecentLoginItem } from "@/api/module_monitor/dashboard";
import FaDashboardSkeleton from "@/components/skeleton/fa-dashboard-skeleton.vue";
import FaBasicBanner from "@/components/banners/fa-basic-banner/index.vue";
import bannerIcon4 from "@imgs/3d/icon4.webp";
import cover2 from "@imgs/cover/img2.webp";

const loading = ref(true);
const workspace = ref<WorkspaceData | null>(null);
const dashboardStats = ref<DashboardStats | null>(null);
const userStore = useUserStore();

const healthList = ref<{ icon: string; class: string; title: string; status: string; time: string }[]>([]);
let healthEventSource: EventSource | null = null;

function connectHealth() {
  const baseURL = import.meta.env.VITE_APP_BASE_API || "";
  const es = new EventSource(`${baseURL}/common/health/stream`);

  es.addEventListener("health", (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      const deps = data.dependencies || {};
      const dbOk = deps.database?.status;
      const redisOk = deps.redis?.status;
      const diskOk = (data.disk_usage ?? 100) < 90;
      healthList.value = [
        {
          icon: "ri:database-2-line",
          class: dbOk ? "bg-success/12 text-success" : "bg-error/12 text-error",
          title: "数据库",
          status: dbOk ? "正常" : "异常",
          time: dbOk ? `${deps.database.latency_ms || 0}ms` : "离线",
        },
        {
          icon: "ri:server-line",
          class: redisOk ? "bg-success/12 text-success" : "bg-error/12 text-error",
          title: "Redis",
          status: redisOk ? "正常" : "异常",
          time: redisOk ? `${deps.redis.latency_ms || 0}ms` : "离线",
        },
        {
          icon: "ri:hard-drive-2-line",
          class: diskOk ? "bg-success/12 text-success" : "bg-error/12 text-error",
          title: "磁盘",
          status: diskOk ? "正常" : "异常",
          time: `${data.disk_usage ?? "-"}%`,
        },
      ];
    } catch {
      /* 静默忽略 */
    }
  });

  es.onerror = () => {
    es.close();
  };
  healthEventSource = es;
}

const isTenantMode = computed(() => userStore.workspaceMode === "tenant");

const tenantStatusStyle = computed(() => {
  if (!workspace.value) return "bg-theme/5!";
  const status = workspace.value.tenant.status;
  if (status === 3 || status === 4) return "bg-error/10!";
  if (status === 2) return "bg-warning/10!";
  if (status === 1) return "bg-info/10!";
  return "bg-theme/5!";
});

const quotaWarning = computed(() => {
  if (!workspace.value) return "";
  const warnings: string[] = [];
  const quota = workspace.value.quota;
  if (quota.usage_percent.users >= 80) {
    warnings.push(`用户用量已达 ${quota.usage_percent.users.toFixed(0)}%`);
  }
  if (quota.usage_percent.roles >= 80) {
    warnings.push(`角色用量已达 ${quota.usage_percent.roles.toFixed(0)}%`);
  }
  if (quota.usage_percent.depts >= 80) {
    warnings.push(`部门用量已达 ${quota.usage_percent.depts.toFixed(0)}%`);
  }
  if (warnings.length > 0) {
    return `${warnings.join("、")}，即将达到套餐上限，请考虑升级套餐`;
  }
  return "";
});

function getQuotaColor(percent: number): string {
  if (percent >= 90) return "#f56c6c";
  if (percent >= 70) return "#e6a23c";
  return "var(--theme-color)";
}

async function loadWorkspace() {
  if (!isTenantMode.value) return;
  try {
    const { data: res } = await TenantAPI.getWorkspace();
    workspace.value = (res?.data as WorkspaceData) || null;
  } catch {
    // ignore
  }
}

async function loadDashboardStats() {
  try {
    const { data: res } = await DashboardAPI.getStats();
    dashboardStats.value = (res?.data as DashboardStats) || null;
    const s = dashboardStats.value;
    if (s) {
      // 更新最近活动
      if (s.recent_logins?.length) {
        dataList.value = s.recent_logins.slice(0, 6).map((log: RecentLoginItem) => ({
          title: log.login_location ? `${log.username} · ${log.login_location}` : log.username,
          status: log.status === 1 ? "成功" : "失败",
          time: log.login_ip || "",
          class: log.status === 1 ? "bg-success/12 text-success" : "bg-error/12 text-error",
          icon: "ri:login-circle-line",
        }));
      }
      // 更新最近交易时间线
      if (s.recent_logins?.length) {
        timelineData.value = s.recent_logins.map((log: RecentLoginItem) => ({
          time: log.login_time
            ? new Date(log.login_time).toLocaleString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })
            : "",
          status: log.status === 1 ? "rgb(73, 190, 255)" : "rgb(255, 105, 105)",
          content: `${log.username} - ${log.status === 1 ? "登录成功" : "登录失败"}`,
        }));
      }
    }
  } catch {
    // ignore
  }
}

onMounted(() => {
  loading.value = false;
  loadWorkspace();
  loadDashboardStats();
  connectHealth();
});

onUnmounted(() => {
  healthEventSource?.close();
});
import FaCardBanner from "@/components/banners/fa-card-banner/index.vue";
import FaImageCard from "@/components/cards/fa-image-card/index.vue";
import FaDataListCard from "@/components/cards/fa-data-list-card/index.vue";
import FaTimelineListCard from "@/components/cards/fa-timeline-list-card/index.vue";
import FaStatsCard from "@/components/cards/fa-stats-card/index.vue";
import FaLineChartCard from "@/components/cards/fa-line-chart-card/index.vue";
import FaBarChartCard from "@/components/cards/fa-bar-chart-card/index.vue";
import FaDonutChartCard from "@/components/cards/fa-donut-chart-card/index.vue";
import FaProgressCard from "@/components/cards/fa-progress-card/index.vue";
import Banner from "./modules/banner.vue";
import NewUser from "./modules/new-user.vue";
import TodoList from "./modules/todo-list.vue";
import CardList from "./modules/card-list.vue";
import AboutProject from "./modules/about-project.vue";
import QuickLinks from "./modules/quick-links.vue";

function handleBannerDemoConfirm() {
  // TODO: 接入真实操作
}
function handleBannerDemoCancel() {
  // TODO: 接入真实操作
}
// === 卡片演示数据 ← workplace ===
const imageCards = {
  id: 1,
  imageUrl: cover2,
  title: "大数据分析助力企业决策的实践案例",
  category: "技术",
  readTime: "3分钟",
  views: 7234,
  comments: 5,
  date: "12月20日 周二",
};

const dataList = ref([
  {
    title: "新加坡之行",
    status: "进行中",
    time: "5分钟",
    class: "bg-theme/12 text-theme",
    icon: "ri:camera-4-line",
  },
  {
    title: "归档数据",
    status: "进行中",
    time: "10分钟",
    class: "bg-secondary/12 text-secondary",
    icon: "ri:bar-chart-box-line",
  },
  {
    title: "客户会议",
    status: "待处理",
    time: "15分钟",
    class: "bg-warning/12 text-warning",
    icon: "ri:user-3-line",
  },
  {
    title: "筛选任务团队",
    status: "进行中",
    time: "20分钟",
    class: "bg-error/12 text-error",
    icon: "ri:account-circle-line",
  },
  {
    title: "发送信封给小王",
    status: "已完成",
    time: "20分钟",
    class: "bg-success/12 text-success",
    icon: "ri:message-3-line",
  },
  {
    title: "筛选任务团队",
    status: "进行中",
    time: "20分钟",
    class: "bg-error/12 text-error",
    icon: "ri:account-circle-line",
  },
]);
const timelineData = ref([
  {
    time: "上午 09:30",
    status: "rgb(73, 190, 255)",
    content: "收到 John Doe 支付的 385.90 美元",
  },
  { time: "上午 10:00", status: "rgb(54, 158, 255)", content: "新销售记录", code: "ML-3467" },
  { time: "上午 12:00", status: "rgb(103, 232, 207)", content: "向 Michael 支付了 64.95 美元" },
  { time: "下午 14:30", status: "rgb(255, 193, 7)", content: "系统维护通知", code: "MT-2023" },
  {
    time: "下午 15:45",
    status: "rgb(255, 105, 105)",
    content: "紧急订单取消提醒",
    code: "OR-9876",
  },
  { time: "下午 17:00", status: "rgb(103, 232, 207)", content: "完成每日销售报表" },
  {
    time: "上午 09:30",
    status: "rgb(73, 190, 255)",
    content: "收到订单 #38291 支付 ¥385.90",
  },
  {
    time: "上午 10:00",
    status: "rgb(54, 158, 255)",
    content: "新商品上架",
    code: "SKU-3467",
  },
  {
    time: "上午 12:00",
    status: "rgb(103, 232, 207)",
    content: "向供应商支付了 ¥6495.00",
  },
  {
    time: "下午 14:30",
    status: "rgb(255, 193, 7)",
    content: "促销活动开始",
    code: "PROMO-2023",
  },
  {
    time: "下午 15:45",
    status: "rgb(255, 105, 105)",
    content: "订单取消提醒",
    code: "ORD-9876",
  },
  {
    time: "下午 17:00",
    status: "rgb(103, 232, 207)",
    content: "完成日销售报表",
  },
]);

function handleMore() {
  ElMessage.info("查看更多");
}
function handleImageCardClick() {
  // TODO: 接入真实跳转
}
</script>

<style scoped lang="scss">
:deep(.el-card) {
  --el-card-border-radius: calc(var(--custom-radius) + 2px);

  border: 1px solid var(--fa-card-border);
}

/* 日程日历 el-calendar 容器 */
.overflow-hidden:deep(.el-card__header) {
  border-bottom-color: var(--el-border-color-extra-light);
}
</style>
