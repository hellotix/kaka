/**
 * 应用入口 —— 装配视图、注入全局回调、决定首屏。
 *
 * 启动顺序只有三件事：
 * 1. bindRouter：把五个渲染函数交给 router.ts。
 *    views 之间跳转只调 nav.xxx()，不 import 彼此，循环依赖就此解开
 *    （装配关系是单向的：main → views → router）。
 * 2. setUnauthorizedHandler：令牌彻底失效（refresh 也失败）时由 api.ts 回调。
 *    api.ts 已经清过本地会话，这里只负责提示 + 回登录页。
 * 3. 按本地是否有 access_token 决定首屏：有就进列表（页面自己会校验并刷新），
 *    没有就进登录页。不做「先请求一次 user/me 再决定」，省一次白屏等待。
 */

import { setUnauthorizedHandler } from './api'
import { bindRouter, nav } from './router'
import { store } from './store'
// 样式在这里 import 而不是 index.html 里 <link>：
// Vite 会把它打进构建产物（带 hash 的 css 文件），开发期也支持热更新
import './style.css'
import { toast } from './ui'
import { renderDetail } from './views/detail'
import { renderForm } from './views/form'
import { renderList } from './views/list'
import { renderLogin } from './views/login'
import { renderProfile } from './views/profile'

bindRouter({
  login: renderLogin,
  list: renderList,
  form: renderForm,
  detail: renderDetail,
  profile: renderProfile,
})

setUnauthorizedHandler(() => {
  toast('登录已过期，请重新登录', 'error')
  nav.login()
})

if (store.isLoggedIn) {
  nav.list()
} else {
  nav.login()
}
