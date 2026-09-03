import type { AlovaGenerics, Method } from 'alova'
import { usePagination } from 'alova/client'
import { computed, ref } from 'vue'

export interface ListPageParams {
  page_no: number
  page_size: number
}

export interface ListPageOptions<AG extends AlovaGenerics = AlovaGenerics> {
  fetcher: (params: ListPageParams) => Method<AG>
  pageSize?: number
  onError?: (error: unknown) => void
}

/**
 * 通用列表分页逻辑（基于 alova usePagination 封装）
 * 底层使用 alova 状态管理，统一暴露 list/total/loading/error 三态与翻页动作
 * 说明：fetcher 需返回 alova Method（http 层 get/post 均为 Method 实例），
 *      请求发送与错误处理完全交给 alova hook 管理
 */
export function useListPage<T, AG extends AlovaGenerics = AlovaGenerics>(options: ListPageOptions<AG>) {
  const { fetcher, pageSize = 10, onError } = options

  const pageParams = ref<ListPageParams>({ page_no: 1, page_size: pageSize })

  const {
    data,
    total,
    loading,
    error,
    send,
    onError: onPageError,
  } = usePagination<AG, T[], any[]>(
    (pageNo: number, pageSizeNo: number) => fetcher({ page_no: pageNo, page_size: pageSizeNo }),
    {
      initialPage: 1,
      initialPageSize: pageSize,
      // 由页面手动触发（onLoad/搜索/翻页），禁用自动监听与预加载
      immediate: false,
      watchingStates: [],
      preloadNextPage: false,
      preloadPreviousPage: false,
      // 列表页总是请求最新数据，禁用 alova 响应缓存
      force: true,
      // 响应已由 http 层 responded 解包为业务结构 { list, total }
      data: res => (res as PageResult<T>).list ?? [],
      total: res => (res as PageResult<T>).total ?? 0,
    },
  )

  onPageError(({ error: e }) => {
    onError?.(e)
  })

  /** 加载当前页数据 */
  async function loadData() {
    try {
      await send(pageParams.value.page_no, pageParams.value.page_size)
    }
    catch {
      // 错误已由 onPageError → onError 统一处理，避免未捕获 Promise 告警
    }
    finally {
      // 收起下拉刷新指示器（onPullDownRefresh → loadData 场景；非刷新场景调用无害）
      uni.stopPullDownRefresh()
    }
  }

  /** 上一页 */
  async function loadPrev() {
    if (pageParams.value.page_no <= 1)
      return
    pageParams.value.page_no -= 1
    await loadData()
  }

  /** 下一页 */
  async function loadNext() {
    pageParams.value.page_no += 1
    await loadData()
  }

  /** 跳回第一页（搜索/重置时使用） */
  async function toFirst() {
    pageParams.value.page_no = 1
    await loadData()
  }

  return {
    list: computed<T[]>(() => data.value ?? []),
    total: computed<number>(() => total.value ?? 0),
    loading,
    error,
    pageParams,
    loadData,
    loadPrev,
    loadNext,
    toFirst,
  }
}
