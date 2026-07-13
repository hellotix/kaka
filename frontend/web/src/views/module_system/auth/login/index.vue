<!-- 登录页：顶栏固定；仅插画列与表单区随布局切换 -->
<template>
  <div class="login-page-root flex h-screen w-full flex-col overflow-hidden" :style="loginBgStyle">
    <FaLoginCenterBackdrop v-if="panelAlign === 'center'" viewport-fixed />
    <FaAuthTopBar v-model:panel-align="panelAlign" @tenant-change="handleTopBarTenantChange" />

    <div
      class="login-auth-split relative z-1 flex min-h-0 flex-1 overflow-hidden"
      :class="`login-auth-split--${panelAlign}`"
    >
      <div
        v-if="panelAlign !== 'center'"
        class="login-auth-split__col login-auth-split__col--illustration"
      >
        <FaLoginLeftView hide-top-branding />
      </div>

      <div
        class="login-auth-split__col login-auth-split__col--form login-page-panel relative flex min-h-0 min-w-0 flex-col"
        :class="panelAlign === 'center' ? 'bg-transparent' : 'bg-(--el-bg-color-page)'"
      >
        <div
          class="login-page-panel__main relative z-1 flex min-h-0 flex-1 flex-col overflow-hidden px-5 pb-2 pt-14 md:px-10 md:pt-18"
        >
          <ElScrollbar>
            <div
              class="login-page-panel__scroll pb-6"
              :class="panelAlign === 'center' && 'login-page-panel__scroll--centered'"
            >
              <div
                class="login-panel-align-row flex w-full items-center justify-center max-sm:min-h-0"
                :class="
                  panelAlign === 'center'
                    ? 'min-h-0 flex-1 py-4'
                    : 'min-h-[min(720px,calc(100vh-13rem))]'
                "
              >
                <div class="auth-right-wrap">
                  <div class="form">
                    <div class="form-intro">
                      <h3 class="title">{{ panelTitle }}</h3>
                      <p class="sub-title">{{ panelSubTitle }}</p>
                    </div>

                    <template v-if="authPanel === 'login'">
                      <template v-if="loginFlowMode === 'account'">
                        <FaLoginAccountForm
                          ref="accountFormRef"
                          v-model:is-passing="isPassing"
                          v-model:is-click-pass="isClickPass"
                          v-model:login-form="loginForm"
                          :rules="rules"
                          :captcha-state="captchaState"
                          :code-loading="codeLoading"
                          :demo-account-key="demoAccountKey"
                          :accounts="accounts"
                          :form-key="formKey"
                          :is-dark="isDark"
                          :drag-verify-text-color="dragVerifyTextColor"
                          :loading="loading"
                          @submit="handleSubmit"
                          @setup-account="setupAccount"
                          @get-captcha="getCaptcha"
                          @open-mobile="openMobileLogin"
                          @open-qr="openQrLogin"
                          @forget="setAuthPanel('forget')"
                          @register="setAuthPanel('register')"
                          @oauth="handleOAuthLogin"
                        />
                      </template>

                      <FaLoginMobilePanel
                        v-else-if="loginFlowMode === 'mobile'"
                        @back="backToAccountLogin"
                        @register="setAuthPanel('register')"
                      />

                      <FaLoginQrPanel
                        v-else-if="loginFlowMode === 'qr'"
                        @back="backToAccountLogin"
                        @register="setAuthPanel('register')"
                      />
                    </template>

                    <FaLoginRegisterPanel
                      v-else-if="authPanel === 'register'"
                      ref="registerPanelRef"
                      v-model:register-agreement-read="registerAgreementRead"
                      v-model:register-form="registerForm"
                      :register-rules="registerRules"
                      :form-key="formKey"
                      :register-loading="registerLoading"
                      :show-email="true"
                      :user-agreement-href="userAgreementHref"
                      @submit="submitRegister"
                      @to-login="setAuthPanel('login')"
                    />

                    <FaLoginForgetPanel
                      v-else
                      ref="forgetPanelRef"
                      v-model:forget-form="forgetForm"
                      :forget-rules="forgetRules"
                      :form-key="formKey"
                      :forget-loading="forgetLoading"
                      @submit="submitForget"
                      @to-login="setAuthPanel('login')"
                    />
                  </div>
                </div>
              </div>
            </div>
          </ElScrollbar>
        </div>

        <footer
          class="login-page-footer login-page-footer--pinned shrink-0 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3"
          :class="panelAlign === 'center' && 'login-page-footer--floating-layout'"
        >
          <div class="login-footer-text text-sm">
            <div class="login-footer-row">
              <a
                :href="configStore.configData?.git_code?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                {{ configStore.configData?.copyright?.config_value || "" }}
              </a>
            </div>
            <span class="login-page-footer__sep login-footer-sep-center">|</span>
            <div class="login-footer-row">
              <a
                :href="configStore.configData?.help_doc?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                帮助
              </a>
              <span class="login-page-footer__sep">|</span>
              <a
                :href="configStore.configData?.privacy?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                隐私
              </a>
              <span class="login-page-footer__sep">|</span>
              <a
                :href="configStore.configData?.clause?.config_value || '#'"
                target="_blank"
                rel="noopener noreferrer"
                class="login-page-footer__link"
              >
                条款
              </a>
              <span
                v-if="configStore.configData?.keep_record?.config_value"
                class="login-page-footer__sep"
                >|</span
              >
              <span
                v-if="configStore.configData?.keep_record?.config_value"
                class="login-page-footer__record"
              >
                {{ configStore.configData.keep_record.config_value }}
              </span>
            </div>
          </div>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { LocationQuery, RouteLocationRaw } from "vue-router";
import AuthAPI, {
  type CaptchaInfo,
  type LoginFormData,
  type OAuthProvider,
} from "@/api/module_system/auth";
import type { TenantRegisterForm } from "@/api/module_system/auth";
import UserAPI, { type ForgetPasswordForm, type RegisterForm } from "@/api/module_system/user";
import { useConfigStore, useAppStore, useSettingsStore, useUserStore } from "@stores";
import { Auth, HttpError, startOAuthLogin } from "@utils";
import { ElMessage, ElNotification, type FormRules } from "element-plus";
import type { Account, AccountKey } from "./types";
import FaLoginAccountForm from "@/components/views/fa-login/forms/FaLoginAccountForm.vue";
import FaLoginForgetPanel from "@/components/views/fa-login/panels/FaLoginForgetPanel.vue";
import FaLoginMobilePanel from "@/components/views/fa-login/panels/FaLoginMobilePanel.vue";
import FaLoginQrPanel from "@/components/views/fa-login/panels/FaLoginQrPanel.vue";
import FaLoginRegisterPanel from "@/components/views/fa-login/panels/FaLoginRegisterPanel.vue";
import FaAuthTopBar from "@/components/views/fa-login/widgets/FaAuthTopBar.vue";
import { useLoginPanelAlign } from "@/components/views/fa-login/composables/useLoginPanelAlign";

defineOptions({ name: "Login" });

type AuthPanel = "login" | "register" | "forget";

/** 登录区内：账号密码 ↔ 手机号 ↔ 扫码（扫码 / 手机号为演示交互） */
type LoginFlowMode = "account" | "mobile" | "qr";

const configStore = useConfigStore();
const settingStore = useSettingsStore();
const appStore = useAppStore();
const { isDark } = storeToRefs(settingStore);
const { t, locale } = useI18n();

const { panelAlign } = useLoginPanelAlign();

const authPanel = ref<AuthPanel>("login");
const loginFlowMode = ref<LoginFlowMode>("account");

const panelTitle = computed(() => {
  if (authPanel.value === "register") return t("login.reg");
  if (authPanel.value === "forget") return t("login.resetPassword");
  if (
    authPanel.value === "login" &&
    (loginFlowMode.value === "mobile" || loginFlowMode.value === "qr")
  ) {
    return t("login.qrLoginTitle");
  }
  return t("login.title");
});

const panelSubTitle = computed(() => {
  if (authPanel.value === "register") return t("register.subTitle");
  if (authPanel.value === "forget") return t("forgetPassword.subTitle");
  if (authPanel.value === "login" && loginFlowMode.value === "mobile") {
    return t("login.mobileLoginSubTitle");
  }
  if (authPanel.value === "login" && loginFlowMode.value === "qr") {
    return t("login.qrLoginSubTitle");
  }
  return t("login.subTitle");
});

const userAgreementHref = computed(() => configStore.configData?.clause?.config_value || "#");

function setAuthPanel(panel: AuthPanel) {
  authPanel.value = panel;
  if (panel !== "login") {
    loginFlowMode.value = "account";
  }
  nextTick(() => {
    accountFormRef.value?.clearValidate?.();
    registerPanelRef.value?.clearValidate?.();
    forgetPanelRef.value?.clearValidate?.();
  });
}

function openMobileLogin() {
  loginFlowMode.value = "mobile";
}

function openQrLogin() {
  loginFlowMode.value = "qr";
}

function backToAccountLogin() {
  loginFlowMode.value = "account";
  nextTick(() => {
    getCaptcha();
    accountFormRef.value?.resetDragVerify?.();
    isPassing.value = false;
    isClickPass.value = false;
  });
}

function handleOAuthLogin(provider: OAuthProvider) {
  startOAuthLogin(provider);
}

async function tryConsumeOAuthCallback() {
  const q = route.query;
  const oauthError = q.oauth_error as string | undefined;
  const access = q.access_token as string | undefined;
  const refresh = q.refresh_token as string | undefined;

  if (!oauthError && !(access && refresh)) return;

  const rest: Record<string, unknown> = { ...q };
  delete rest.oauth_error;
  delete rest.access_token;
  delete rest.refresh_token;
  delete rest.token_type;

  if (oauthError) {
    ElMessage.error(decodeURIComponent(oauthError));
    await router.replace({ path: route.path, query: rest as LocationQuery });
    return;
  }

  if (access && refresh) {
    try {
      Auth.setTokens(access, refresh, true);
      userStore.setToken(access, refresh);
      userStore.setLoginStatus(true);
      ElNotification({
        title: t("login.oauthNoticeTitle"),
        message: t("login.oauthLoginSuccess"),
        type: "success",
      });
      await router.replace(resolveRedirectTarget(rest as LocationQuery));
      if (settingStore.showGuide) {
        appStore.showGuide(true);
      }
    } catch (error) {
      console.error("[Login] OAuth callback:", error);
      ElMessage.error(t("login.oauthLoginFailed"));
      await router.replace({ path: route.path, query: rest as LocationQuery });
    }
  }
}

const dragVerifyTextColor = computed(() =>
  isDark.value ? "rgba(255, 255, 255, 0.45)" : "var(--fa-gray-700)"
);
const formKey = ref(0);

watch(locale, () => {
  formKey.value++;
});

watch(authPanel, (panel) => {
  if (panel !== "login") return;
  if (loginFlowMode.value !== "account") return;
  getCaptcha();
  accountFormRef.value?.resetDragVerify?.();
  isPassing.value = false;
  isClickPass.value = false;
});

const accounts = computed<Account[]>(() => [
  {
    key: "super",
    label: t("login.roles.super"),
    username: "super",
    password: "123456",
    roles: ["R_SUPER"],
  },
  {
    key: "admin",
    label: t("login.roles.admin"),
    username: "admin",
    password: "123456",
    roles: ["R_ADMIN"],
  },
  {
    key: "user",
    label: t("login.roles.user"),
    username: "user",
    password: "123456",
    roles: ["R_USER"],
  },
]);

const demoAccountKey = ref<AccountKey>("super");
const userStore = useUserStore();
const router = useRouter();
const route = useRoute();
const isPassing = ref(false);
const isClickPass = ref(false);

const accountFormRef = ref<InstanceType<typeof FaLoginAccountForm> | null>(null);
const registerPanelRef = ref<InstanceType<typeof FaLoginRegisterPanel> | null>(null);
const forgetPanelRef = ref<InstanceType<typeof FaLoginForgetPanel> | null>(null);

const loading = ref(false);
const registerLoading = ref(false);
const forgetLoading = ref(false);
const codeLoading = ref(false);

const registerAgreementRead = ref(false);

const registerForm = reactive<RegisterForm & { email: string }>({
  tenant_name: "",
  username: "",
  password: "",
  confirmPassword: "",
  email: "",
});

const forgetForm = reactive<ForgetPasswordForm>({
  tenant_name: "",
  username: "",
  new_password: "",
  confirmPassword: "",
});

const validateRegisterPassword = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error(t("login.message.password.required")));
    return;
  }
  if (registerForm.confirmPassword) {
    registerPanelRef.value?.validateField?.("confirmPassword");
  }
  callback();
};

const validateRegisterConfirm = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error(t("login.message.password.required")));
    return;
  }
  if (value !== registerForm.password) {
    callback(new Error(t("login.message.password.inconformity")));
    return;
  }
  callback();
};

const registerRules = computed<FormRules<RegisterForm & { email: string }>>(() => ({
  tenant_name: [
    { required: true, message: t("login.message.tenantName.required"), trigger: "blur" },
  ],
  username: [{ required: true, message: t("login.message.username.required"), trigger: "blur" }],
  password: [
    { required: true, validator: validateRegisterPassword, trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: t("login.message.password.required"), trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
    { validator: validateRegisterConfirm, trigger: "blur" },
  ],
  email: [
    { required: true, message: t("login.email.required"), trigger: "blur" },
    {
      type: "email",
      message: t("login.email.invalid"),
      trigger: "blur",
    },
  ],
}));

const validateForgetConfirm = (_rule: unknown, value: string, callback: (e?: Error) => void) => {
  if (!value) {
    callback(new Error(t("login.message.password.required")));
    return;
  }
  if (value !== forgetForm.new_password) {
    callback(new Error(t("login.message.password.inconformity")));
    return;
  }
  callback();
};

const forgetRules = computed<FormRules<ForgetPasswordForm>>(() => ({
  tenant_name: [
    { required: true, message: t("login.message.tenantName.required"), trigger: "blur" },
  ],
  username: [{ required: true, message: t("login.message.username.required"), trigger: "blur" }],
  new_password: [
    { required: true, message: t("login.message.password.required"), trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
  ],
  confirmPassword: [
    { required: true, message: t("login.message.password.required"), trigger: "blur" },
    { min: 6, message: t("login.message.password.min"), trigger: "blur" },
    { validator: validateForgetConfirm, trigger: "blur" },
  ],
}));

const loginForm = reactive<LoginFormData>({
  username: "",
  password: "",
  captcha_key: "",
  remember: true,
  login_type: "PC端",
});

// ── 租户品牌 ──
const loginBgStyle = computed(() => {
  const bg = configStore.configData?.login_bg?.config_value?.trim();
  return bg
    ? { backgroundImage: `url(${bg})`, backgroundSize: "cover", backgroundPosition: "center" }
    : {};
});
const currentTenantId = ref(1);
const isTenantResolved = ref(false); // 是否已自动识别到租户

/** 解析当前域名，提取子域名作为租户编码 */
function extractSubdomain(hostname: string): string | null {
  if (
    !hostname ||
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    /^\d+\.\d+\.\d+\.\d+$/.test(hostname)
  ) {
    return null;
  }
  const parts = hostname.split(".");
  // 排除二级域名如 "xxx.com"、"xxx.cn"（只有两段）
  // 排除 "www.xxx.com"（子域名为 www）
  if (parts.length < 3) return null;
  const sub = (parts[0] as string).toLowerCase();
  // 排除常见系统前缀
  if (["www", "admin", "app", "api", "mail", "dev", "test", "stage"].includes(sub)) return null;
  return sub;
}

/** 自动识别租户（四级策略：URL 参数 > 自定义域名 > 通配符子域名 > 默认） */
async function autoDetectTenant() {
  // 优先级 1：URL 参数 ?tenant=xxx
  const queryTenant = route.query.tenant as string | undefined;
  if (queryTenant?.trim()) {
    await loadTenantByCode(queryTenant.trim());
    return;
  }

  const hostname = window.location.hostname;

  // 优先级 2：自定义域名 — 完整域名匹配 TenantModel.domain
  if (
    hostname &&
    hostname !== "localhost" &&
    hostname !== "127.0.0.1" &&
    !/^\d+\.\d+\.\d+\.\d+$/.test(hostname)
  ) {
    try {
      const { data: res } = await AuthAPI.lookupTenantByDomain(hostname);
      const info = res?.data as Record<string, any> | undefined;
      if (info?.id) {
        currentTenantId.value = Number(info.id);
        await configStore.getConfig(true, currentTenantId.value);
        isTenantResolved.value = true;
        return;
      }
    } catch {
      // 未匹配自定义域名，继续下一步
    }
  }

  // 优先级 3：通配符子域名 — 提取子域名匹配 TenantModel.code
  const subdomain = extractSubdomain(hostname);
  if (subdomain) {
    await loadTenantByCode(subdomain, false);
    if (isTenantResolved.value) return;
  }

  // 优先级 4：使用系统默认配置
  isTenantResolved.value = false;
}

/** 根据编码查询租户并加载配置 */
async function loadTenantByCode(code: string, markResolved = true) {
  try {
    const { data: res } = await AuthAPI.lookupTenant(code);
    const info = res?.data as Record<string, any> | undefined;
    if (info?.id) {
      currentTenantId.value = Number(info.id);
      await configStore.getConfig(true, currentTenantId.value);
      if (markResolved) isTenantResolved.value = true;
      return;
    }
  } catch {
    // 静默失败
  }
  if (markResolved) isTenantResolved.value = false;
}

const captchaState = reactive<CaptchaInfo>({
  enable: false,
  key: "",
  img_base: "",
});

const rules = computed<FormRules>(() => {
  const base: FormRules = {
    username: [
      {
        required: true,
        trigger: "blur",
        message: t("login.message.username.required"),
      },
    ],
    password: [
      {
        required: true,
        trigger: "blur",
        message: t("login.message.password.required"),
      },
      {
        min: 6,
        message: t("login.message.password.min"),
        trigger: "blur",
      },
    ],
  };
  return base;
});

function setupAccount(key: AccountKey) {
  const selected = accounts.value.find((a: Account) => a.key === key);
  demoAccountKey.value = key;
  loginForm.username = selected?.username ?? "";
  loginForm.password = selected?.password ?? "";
}

async function getCaptcha() {
  try {
    codeLoading.value = true;
    const response = await AuthAPI.getCaptcha();
    const data = response.data.data;
    loginForm.captcha_key = data.key;
    captchaState.img_base = data.img_base;
    captchaState.enable = data.enable;
    // 重置滑块状态
    isPassing.value = false;
    isClickPass.value = false;
  } catch {
    captchaState.enable = false;
    loginForm.captcha_key = "";
  } finally {
    codeLoading.value = false;
  }
}

/** 滑块验证完成后通知后端标记 */
async function handleSliderPass(passed: boolean) {
  if (!passed || !loginForm.captcha_key) return;
  try {
    await AuthAPI.sliderComplete(loginForm.captcha_key);
  } catch {
    isPassing.value = false;
    await getCaptcha();
  }
}

/** 监听滑块通过状态 */
watch(isPassing, (val) => {
  handleSliderPass(val);
});

/** 顶部栏租户切换 */
async function handleTopBarTenantChange(tenantId: number) {
  currentTenantId.value = tenantId;
  isTenantResolved.value = true;
  await configStore.getConfig(true, tenantId);
}

function resolveRedirectTarget(query: LocationQuery): RouteLocationRaw {
  const defaultPath = "/";
  const rawRedirect = (query.redirect as string) || defaultPath;
  try {
    const resolved = router.resolve(rawRedirect);
    return {
      path: resolved.path,
      query: resolved.query,
    };
  } catch {
    return { path: defaultPath };
  }
}

let notificationInstance: ReturnType<typeof ElNotification> | null = null;

const showVoteNotification = () => {
  notificationInstance = ElNotification({
    title: "⭐ FastapiAdmin 完全开源 · 期待您的 Star 支持 🙏",
    message: `项目持续迭代中，若对您有所帮助，欢迎点亮 Star 支持！
    <br/><a href="https://github.com/fastapiadmin/FastapiAdmin" target="_blank" style="color: var(--el-color-primary); text-decoration: none; font-weight: 500;">Github仓库 →</a>
    <br/><a href="https://gitee.com/fastapiadmin/FastapiAdmin" target="_blank" style="color: var(--el-color-warning); text-decoration: none; font-weight: 500;">Gitee仓库 →</a>`,
    type: "success",
    position:
      panelAlign.value === "right" || panelAlign.value === "center"
        ? "bottom-left"
        : "bottom-right",
    duration: 0,
    dangerouslyUseHTMLString: true,
  });
};

let voteTimer: ReturnType<typeof setTimeout> | null = null;

onMounted(async () => {
  setupAccount("super");
  await configStore.getConfig(true);
  await autoDetectTenant();
  await tryConsumeOAuthCallback();
  if (userStore.isLogin) {
    await router.replace(resolveRedirectTarget(route.query));
    return;
  }
  getCaptcha();
  voteTimer = setTimeout(showVoteNotification, 500);
});

onActivated(() => {
  if (authPanel.value !== "login" || loginFlowMode.value !== "account") return;
  getCaptcha();
});

onBeforeUnmount(() => {
  if (voteTimer !== null) clearTimeout(voteTimer);
  notificationInstance?.close();
  notificationInstance = null;
});

watch(
  () => route.fullPath,
  () => {
    if (authPanel.value !== "login" || loginFlowMode.value !== "account") return;
    getCaptcha();
  }
);

const handleSubmit = async () => {
  if (!accountFormRef.value) return;

  try {
    const valid = await accountFormRef.value.validate?.();
    if (!valid) return;

    if (!isPassing.value) {
      isClickPass.value = true;
      return;
    }

    loading.value = true;

    await userStore.login(loginForm);
    await router.replace(resolveRedirectTarget(route.query));

    if (settingStore.showGuide) {
      appStore.showGuide(true);
    }
  } catch (error) {
    // 自增 formKey 强制重新挂载表单（滑块自动重置为初始状态）
    formKey.value++;
    await getCaptcha();
    if (!(error instanceof HttpError)) {
      console.error("[Login] Unexpected error:", error);
      ElNotification({
        title: "提示",
        message: error instanceof Error ? error.message : String(error),
        type: "error",
      });
    }
  } finally {
    loading.value = false;
  }
};

async function submitRegister() {
  if (!registerAgreementRead.value) {
    ElMessage.warning(t("login.message.agree.required"));
    return;
  }
  if (!registerPanelRef.value) return;
  try {
    await registerPanelRef.value.validate?.();
    registerLoading.value = true;
    // 租户自助注册（PRD §4.5）
    const regData: TenantRegisterForm = {
      tenant_name: registerForm.tenant_name,
      username: registerForm.username,
      password: registerForm.password,
      email: registerForm.email,
    };
    await AuthAPI.tenantRegister(regData);
    // 注册成功后自动填充登录表单并提交
    loginForm.username = registerForm.username;
    loginForm.password = registerForm.password;
    registerForm.tenant_name = "";
    registerForm.username = "";
    registerForm.password = "";
    registerForm.confirmPassword = "";
    registerForm.email = "";
    registerAgreementRead.value = false;
    setAuthPanel("login");
    await handleSubmit();
  } catch (error) {
    console.error("[Login] register:", error);
  } finally {
    registerLoading.value = false;
  }
}

async function submitForget() {
  if (!forgetPanelRef.value) return;
  try {
    await forgetPanelRef.value.validate?.();
    forgetLoading.value = true;
    await UserAPI.forgetPassword(forgetForm);
    loginForm.username = forgetForm.username;
    loginForm.password = forgetForm.new_password;
    forgetForm.tenant_name = "";
    forgetForm.username = "";
    forgetForm.new_password = "";
    forgetForm.confirmPassword = "";
    setAuthPanel("login");
  } catch (error) {
    console.error("[Login] forget password:", error);
  } finally {
    forgetLoading.value = false;
  }
}
</script>

<style scoped lang="scss">
@use "../../../../components/views/fa-login/fa-login";
</style>
