/**
 * 会话相关的共享动作 —— 登录页、首页、详情页都要用，集中在这里。
 */

import { api } from './api'
import { store } from './store'
import type { FamilyBrief } from './types'

/**
 * 拉取「我的家庭」列表并写入会话。
 *
 * 每次进入首页都刷一遍：家庭可能刚被创建/加入，也可能被解散或把自己移出，
 * 本地缓存的列表会过期（store.setFamilies 会在当前家庭失效时自动回退）。
 */
export async function refreshFamilies(): Promise<FamilyBrief[]> {
  const list = await api.myFamilies()
  store.setFamilies(list)
  return list
}

/** 退出登录：通知后端作废会话；后端不可用时也照样清本地（否则用户被困在登录态里） */
export async function doLogout(): Promise<void> {
  try {
    await api.logout()
  } catch {
    // 忽略：本地会话该清还是要清
  }
  store.clear()
}
