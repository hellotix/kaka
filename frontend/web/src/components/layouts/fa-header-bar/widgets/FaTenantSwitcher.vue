<!-- 工作区模式切换器：平台模式 → 进入租户 | 租户模式 → 返回平台 -->
<template>
  <!-- 平台管理模式："进入租户"按钮 -->
  <ElDropdown
    v-if="isPlatformMode && tenantList.length > 0"
    trigger="click"
    placement="bottom-start"
    :disabled="switching"
    @command="handleEnterTenant"
    @visible-change="(v) => (dropdownVisible = v)"
    popper-class="fa-tenant-dropdown"
  >
    <div
      class="tenant-switcher workspace-entry"
      :class="{ 'is-active': dropdownVisible, 'is-switching': switching }"
      title="进入租户工作区"
    >
      <FaSvgIcon icon="ri:building-2-fill" class="icon" />
      <span class="name">进入租户</span>
      <FaSvgIcon
        v-if="!switching"
        icon="ri:arrow-down-s-line"
        class="arrow"
        :class="{ rotated: dropdownVisible }"
      />
      <ElIcon v-else class="arrow is-loading"><Loading /></ElIcon>
    </div>
    <template #dropdown>
      <ElDropdownMenu>
        <div class="dropdown-header">
          <span class="dropdown-title">选择要进入的租户</span>
          <ElTag size="small" effect="plain" type="info"> 共 {{ tenantList.length }} 个 </ElTag>
        </div>
        <ElDropdownItem v-for="t in tenantList" :key="t.id" :command="t.id" :disabled="switching">
          <div class="dropdown-item">
            <div class="item-main">
              <FaSvgIcon icon="ri:building-2-line" class="item-icon" />
              <div class="item-text">
                <div class="item-name">{{ t.name }}</div>
                <div v-if="t.code" class="item-code">{{ t.code }}</div>
              </div>
            </div>
            <FaSvgIcon icon="ri:arrow-right-s-line" class="item-enter-icon" />
          </div>
        </ElDropdownItem>
        <div class="dropdown-footer-hint">
          <FaSvgIcon icon="ri:information-line" class="hint-icon" />
          <span>进入后可查看该租户的数据和菜单</span>
        </div>
        <div v-if="switching" class="dropdown-footer">
          <ElIcon class="is-loading"><Loading /></ElIcon>
          <span>进入中...</span>
        </div>
      </ElDropdownMenu>
    </template>
  </ElDropdown>

  <!-- 租户工作区模式：显示当前租户 + 返回平台（仅超管可见） -->
  <ElDropdown
    v-else-if="!isPlatformMode && isSuperuser"
    trigger="click"
    placement="bottom-start"
    :disabled="switching"
    @command="handleCommand"
    @visible-change="(v) => (dropdownVisible = v)"
    popper-class="fa-tenant-dropdown"
  >
    <div
      class="tenant-switcher"
      :class="{ 'is-active': dropdownVisible, 'is-switching': switching }"
      :title="'当前工作区：' + displayTenantName"
    >
      <FaSvgIcon icon="ri:building-2-fill" class="icon" />
      <span class="name">{{ displayTenantName }}</span>
      <FaSvgIcon
        v-if="!switching"
        icon="ri:arrow-down-s-line"
        class="arrow"
        :class="{ rotated: dropdownVisible }"
      />
      <ElIcon v-else class="arrow is-loading"><Loading /></ElIcon>
    </div>
    <template #dropdown>
      <ElDropdownMenu>
        <div class="dropdown-header">
          <span class="dropdown-title">当前工作区</span>
          <ElTag size="small" effect="plain" type="success"> 租户 </ElTag>
        </div>
        <div class="dropdown-current-info">
          <FaSvgIcon icon="ri:building-2-fill" class="current-icon" />
          <div class="current-text">
            <div class="current-name">{{ displayTenantName }}</div>
            <div v-if="workspaceTenant?.code" class="current-code">
              {{ workspaceTenant.code }}
            </div>
          </div>
        </div>
        <div class="dropdown-divider" />
        <ElDropdownItem command="exitPlatform" :disabled="switching">
          <div class="dropdown-item exit-action">
            <FaSvgIcon icon="ri:arrow-go-back-fill" class="item-icon exit-icon" />
            <div class="item-text">
              <div class="item-name">返回平台管理</div>
              <div class="item-code">回到平台管理视角</div>
            </div>
          </div>
        </ElDropdownItem>
        <div v-if="switching" class="dropdown-footer">
          <ElIcon class="is-loading"><Loading /></ElIcon>
          <span>切换中...</span>
        </div>
      </ElDropdownMenu>
    </template>
  </ElDropdown>

  <!-- 普通租户用户：仅显示当前租户名（无下拉） -->
  <div
    v-else-if="!isPlatformMode"
    class="tenant-switcher tenant-display"
    :title="'当前租户：' + displayTenantName"
  >
    <FaSvgIcon icon="ri:building-2-fill" class="icon" />
    <span class="name">{{ displayTenantName }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { useUserStore } from "@stores";
import { storeToRefs } from "pinia";

defineOptions({ name: "FaTenantSwitcher" });

const userStore = useUserStore();
const { tenantList, isPlatformMode, workspaceMode, workspaceTenant, currentTenant, info } =
  storeToRefs(userStore);

const dropdownVisible = ref(false);
const switching = ref(false);

/** 是否为超管（判断是否显示"返回平台"入口） */
const isSuperuser = computed(() => !!info.value?.is_superuser);

/** 当前显示的工作区名称 */
const displayTenantName = computed(() => {
  if (isPlatformMode.value) return "平台管理";
  return (
    workspaceTenant.value?.name || currentTenant.value?.name || info.value?.tenant_by?.name || "—"
  );
});

/** 平台模式：进入租户工作区（平台管理员使用代签入） */
async function handleEnterTenant(tenantId: number) {
  if (switching.value) return;
  const tenant = tenantList.value.find((t) => t.id === tenantId);
  if (!tenant) return;
  switching.value = true;
  dropdownVisible.value = false;
  try {
    if (isSuperuser.value) {
      await userStore.impersonate(tenantId);
    } else {
      await userStore.selectTenant(tenantId);
    }
    workspaceMode.value = "tenant";
    workspaceTenant.value = tenant;
    setTimeout(() => window.location.reload(), 200);
  } catch {
    switching.value = false;
  }
}

/** 租户模式：处理下拉命令 */
async function handleCommand(command: string) {
  if (command === "exitPlatform") {
    if (switching.value) return;
    switching.value = true;
    dropdownVisible.value = false;
    try {
      await userStore.exitTenantWorkspace();
      setTimeout(() => window.location.reload(), 200);
    } catch {
      switching.value = false;
    }
  }
}
</script>

<style scoped>
.tenant-switcher {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  max-width: 180px;
  height: 32px;
  padding: 0 10px;
  font-size: 13px;

  @media (width <= 640px) {
    max-width: 120px;
    padding: 0 8px;
    font-size: 12px;
  }

  color: var(--el-text-color-primary);
  cursor: pointer;
  user-select: none;
  background: var(--fa-gray-100);
  border: 1px solid var(--fa-gray-300);
  border-radius: 6px;
  transition: all 0.15s;

  &:hover {
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary-light-5);
  }

  &.is-active {
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary);
  }

  &.is-switching {
    cursor: wait;
    opacity: 0.7;
  }

  &.workspace-entry {
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    border-color: var(--el-color-primary-light-5);

    &:hover {
      color: #fff;
      background: var(--el-color-primary);
      border-color: var(--el-color-primary);
    }
  }

  &.tenant-display {
    cursor: default;
  }

  .icon {
    flex-shrink: 0;
    font-size: 14px;
  }

  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-weight: 500;
    white-space: nowrap;
  }

  .arrow {
    flex-shrink: 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    transition: transform 0.2s;

    &.rotated {
      transform: rotate(180deg);
    }
  }
}
</style>

<style lang="scss">
/* 全局样式：下拉面板 */
.fa-tenant-dropdown {
  min-width: 240px;
  max-width: calc(100vw - 20px);
  padding: 0 !important;

  @media (width <= 640px) {
    width: 90vw;
    min-width: 200px;
  }

  .el-dropdown-menu__item {
    padding: 0 !important;

    &:not(.is-disabled):hover {
      background: var(--fa-gray-200) !important;
    }
  }

  .dropdown-header {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--el-border-color-lighter);
  }

  .dropdown-title {
    font-size: 12px;
    font-weight: 500;
    color: var(--el-text-color-secondary);
  }

  .dropdown-divider {
    height: 1px;
    margin: 4px 0;
    background: var(--el-border-color-lighter);
  }

  .dropdown-current-info {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 10px 12px;

    .current-icon {
      flex-shrink: 0;
      font-size: 20px;
      color: var(--el-color-primary);
    }

    .current-text {
      min-width: 0;
    }

    .current-name {
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 14px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      white-space: nowrap;
    }

    .current-code {
      margin-top: 2px;
      font-size: 11px;
      color: var(--el-text-color-secondary);
    }
  }

  .dropdown-item {
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 8px 12px;
    border-radius: 0;
    transition: all 0.15s;

    &.exit-action {
      &:hover {
        .exit-icon {
          color: var(--el-color-danger);
        }
      }
    }
  }

  .dropdown-footer-hint {
    display: flex;
    gap: 4px;
    align-items: center;
    justify-content: center;
    padding: 6px 12px 8px;
    font-size: 11px;
    color: var(--el-text-color-secondary);
    border-top: 1px solid var(--el-border-color-lighter);

    .hint-icon {
      font-size: 12px;
    }
  }

  .item-main {
    display: flex;
    flex: 1;
    gap: 8px;
    align-items: center;
    min-width: 0;
  }

  .item-icon {
    flex-shrink: 0;
    font-size: 15px;
    color: var(--el-text-color-secondary);
  }

  .item-enter-icon {
    flex-shrink: 0;
    font-size: 14px;
    color: var(--el-color-primary);
  }

  .exit-icon {
    flex-shrink: 0;
    font-size: 15px;
    color: var(--el-text-color-secondary);
  }

  .item-text {
    min-width: 0;
  }

  .item-name {
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 13px;
    font-weight: 500;
    color: var(--el-text-color-primary);
    white-space: nowrap;
  }

  .item-code {
    margin-top: 2px;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 11px;
    color: var(--el-text-color-secondary);
    white-space: nowrap;
  }

  .dropdown-footer {
    display: flex;
    gap: 6px;
    align-items: center;
    justify-content: center;
    padding: 8px 12px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    border-top: 1px solid var(--el-border-color-lighter);
  }
}
</style>
