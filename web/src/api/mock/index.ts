import MockAdapter from 'axios-mock-adapter'
import dayjs from 'dayjs'
import { http } from '@/api/http'
import type { Pagination } from '@/types'
import {
  mockUsers,
  mockPosts,
  mockComments,
  mockNotifications,
  mockHotSearches,
  CURRENT_USER_ID,
  mockLikedPostIds,
  mockFollowingIds,
  mockFollowerIds,
} from './data'

/**
 * Mock 适配层：拦截 http 实例的全部请求，返回与后端一致的信封结构。
 * VITE_USE_MOCK=false 时此文件不会被调用，前端无缝切到真实后端。
 */
export function setupMock() {
  const mock = new MockAdapter(http, { delayResponse: 260 })
  const ok = (data: unknown): [number, unknown] => [200, { code: 200, data, message: 'success' }]

  const paginate = <T>(list: T[], page = 1, perPage = 20): { items: T[]; pagination: Pagination } => {
    const total = list.length
    const pages = Math.max(1, Math.ceil(total / perPage))
    const items = list.slice((page - 1) * perPage, page * perPage)
    return {
      items,
      pagination: { page, per_page: perPage, total, pages, has_next: page < pages, has_prev: page > 1 },
    }
  }

  const currentUser = () => mockUsers.find((u) => u.id === CURRENT_USER_ID)!

  /* ------------------------------ users ------------------------------ */
  mock.onPost('/users/login').reply((config) => {
    const body = JSON.parse(config.data || '{}')
    if (!body.username || !body.password) {
      return [400, { code: 400, error: '参数校验失败: 用户名和密码不能为空', request_id: 'mock-req' }]
    }
    return ok({ access_token: 'mock-access-' + Date.now(), refresh_token: 'mock-refresh-' + Date.now() })
  })

  mock.onPost('/users/register').reply((config) => {
    const body = JSON.parse(config.data || '{}')
    if (!body.username || !body.email || !body.password) {
      return [400, { code: 400, error: '参数校验失败: 请填写完整', request_id: 'mock-req' }]
    }
    return ok({ access_token: 'mock-access-' + Date.now(), refresh_token: 'mock-refresh-' + Date.now() })
  })

  mock.onPost('/users/refresh').reply(() => ok({ access_token: 'mock-access-' + Date.now() }))
  mock.onPost('/users/logout').reply(() => ok({}))
  mock.onGet('/users/me').reply(() => ok(currentUser()))

  /* ------------------------------ posts ------------------------------ */
  // 注意：具体路径必须先于 /posts/:id 正则注册
  mock.onGet('/posts/hot-searches').reply((config) => {
    const size = Number(config.params?.size) || 10
    return ok({ items: mockHotSearches.slice(0, size) })
  })

  mock.onGet('/posts/search/suggestions').reply((config) => {
    const q = String(config.params?.q || '')
    const fromHot = mockHotSearches.map((h) => h.keyword).filter((k) => k.includes(q))
    const fromUsers = mockUsers.map((u) => u.username).filter((n) => n.includes(q))
    return ok({ items: [...fromHot, ...fromUsers].slice(0, 8) })
  })

  mock.onGet('/posts/search').reply((config) => {
    const q = String(config.params?.q || '')
    const page = Number(config.params?.page) || 1
    const perPage = Number(config.params?.per_page) || 20
    let list = mockPosts.filter(
      (p) => p.content.includes(q) || p.username.includes(q),
    )
    if (config.params?.sort === 'hot') list = [...list].sort((a, b) => b.like_count - a.like_count)
    const { items, pagination } = paginate(list, page, perPage)
    return ok({ posts: items, pagination, liked_post_ids: [...mockLikedPostIds] })
  })

  mock.onGet('/posts').reply((config) => {
    const page = Number(config.params?.page) || 1
    const perPage = Number(config.params?.per_page) || 20
    const userId = config.params?.user_id
    let list = [...mockPosts].sort((a, b) => +dayjs(b.created_at) - +dayjs(a.created_at))
    if (userId) list = list.filter((p) => String(p.user_id) === String(userId))
    const { items, pagination } = paginate(list, page, perPage)
    return ok({ posts: items, pagination, liked_post_ids: [...mockLikedPostIds] })
  })

  mock.onPost('/posts').reply((config) => {
    const body = JSON.parse(config.data || '{}')
    const content = String(body.content || '').trim()
    if (!content) return [400, { code: 400, error: '帖子内容不能为空', request_id: 'mock-req' }]
    if (content.length > 1000) return [400, { code: 400, error: '帖子内容不能超过1000个字符', request_id: 'mock-req' }]
    const me = currentUser()
    const post = {
      id: Math.max(0, ...mockPosts.map((p) => p.id)) + 1,
      user_id: me.id,
      username: me.username,
      content,
      image_url: body.image_url || null,
      like_count: 0,
      comment_count: 0,
      created_at: dayjs().toISOString(),
    }
    mockPosts.unshift(post)
    return ok(post)
  })

  mock.onGet(/\/posts\/\d+$/).reply((config) => {
    const id = Number(config.url!.split('/').pop())
    const post = mockPosts.find((p) => p.id === id)
    if (!post) return [404, { code: 404, error: '帖子不存在', request_id: 'mock-req' }]
    return ok({ post, has_liked: mockLikedPostIds.has(id) })
  })

  mock.onPut(/\/posts\/\d+$/).reply((config) => {
    const id = Number(config.url!.split('/').pop())
    const post = mockPosts.find((p) => p.id === id)
    if (!post) return [404, { code: 404, error: '帖子不存在', request_id: 'mock-req' }]
    const body = JSON.parse(config.data || '{}')
    if (body.content) post.content = String(body.content).trim()
    if (body.image_url !== undefined) post.image_url = body.image_url
    return ok(post)
  })

  mock.onDelete(/\/posts\/\d+$/).reply((config) => {
    const id = Number(config.url!.split('/').pop())
    const idx = mockPosts.findIndex((p) => p.id === id)
    if (idx === -1) return [404, { code: 404, error: '帖子不存在', request_id: 'mock-req' }]
    mockPosts.splice(idx, 1)
    return ok({})
  })

  /* ------------------------------ comments ------------------------------ */
  mock.onGet(/\/comments\/posts\/\d+\/comments/).reply((config) => {
    const postId = Number(config.url!.match(/posts\/(\d+)/)![1])
    const page = Number(config.params?.page) || 1
    const perPage = Number(config.params?.per_page) || 20
    const list = mockComments
      .filter((c) => c.post_id === postId)
      .sort((a, b) => +dayjs(a.created_at) - +dayjs(b.created_at))
    return ok(paginate(list, page, perPage))
  })

  mock.onPost('/comments').reply((config) => {
    const body = JSON.parse(config.data || '{}')
    const me = currentUser()
    const comment = {
      id: Math.max(100, ...mockComments.map((c) => c.id)) + 1,
      post_id: Number(body.post_id),
      user_id: me.id,
      username: me.username,
      content: String(body.content || '').trim(),
      like_count: 0,
      created_at: dayjs().toISOString(),
    }
    mockComments.push(comment)
    const post = mockPosts.find((p) => p.id === comment.post_id)
    if (post) post.comment_count += 1
    return ok(comment)
  })

  mock.onDelete(/\/comments\/\d+$/).reply((config) => {
    const id = Number(config.url!.split('/').pop())
    const idx = mockComments.findIndex((c) => c.id === id)
    if (idx !== -1) mockComments.splice(idx, 1)
    return ok({})
  })

  /* ------------------------------ likes ------------------------------ */
  mock.onPost(/\/likes\/posts\/\d+\/likes/).reply((config) => {
    const postId = Number(config.url!.match(/posts\/(\d+)/)![1])
    const post = mockPosts.find((p) => p.id === postId)
    if (post && !mockLikedPostIds.has(postId)) {
      mockLikedPostIds.add(postId)
      post.like_count += 1
    }
    return ok({})
  })

  // 新契约：按 (user_id, post_id) 幂等取消点赞
  mock.onDelete(/\/likes\/posts\/\d+\/likes$/).reply((config) => {
    const postId = Number(config.url!.match(/posts\/(\d+)/)![1])
    const post = mockPosts.find((p) => p.id === postId)
    if (post && mockLikedPostIds.has(postId)) {
      mockLikedPostIds.delete(postId)
      post.like_count = Math.max(0, post.like_count - 1)
    }
    return ok({})
  })

  mock.onGet('/likes/my-likes').reply((config) => {
    const page = Number(config.params?.page) || 1
    const perPage = Number(config.params?.per_page) || 20
    const list = mockPosts.filter((p) => mockLikedPostIds.has(p.id))
    return ok(paginate(list, page, perPage))
  })

  /* ------------------------------ follows ------------------------------ */
  const toUserCards = (ids: number[]) =>
    ids.map((id) => mockUsers.find((u) => u.id === id)!).filter(Boolean)

  mock.onGet('/follows/followers').reply((config) => {
    const { items, pagination } = paginate(
      toUserCards(mockFollowerIds),
      Number(config.params?.page) || 1,
      Number(config.params?.per_page) || 20,
    )
    return ok({ items, pagination })
  })

  mock.onGet('/follows/following/list').reply((config) => {
    const { items, pagination } = paginate(
      toUserCards([...mockFollowingIds]),
      Number(config.params?.page) || 1,
      Number(config.params?.per_page) || 20,
    )
    return ok({ items, pagination })
  })

  mock.onGet('/follows/following/mutual').reply((config) => {
    const mutual = [...mockFollowingIds].filter((id) => mockFollowerIds.includes(id))
    const { items, pagination } = paginate(
      toUserCards(mutual),
      Number(config.params?.page) || 1,
      Number(config.params?.per_page) || 20,
    )
    return ok({ items, pagination })
  })

  mock.onPost('/follows/following').reply((config) => {
    const body = JSON.parse(config.data || '{}')
    mockFollowingIds.add(Number(body.followed_id))
    return ok({})
  })

  mock.onDelete(/\/follows\/following\/\d+$/).reply((config) => {
    const id = Number(config.url!.split('/').pop())
    mockFollowingIds.delete(id)
    return ok({})
  })

  /* ------------------------------ notifications ------------------------------ */
  mock.onGet('/notifications').reply((config) => {
    const page = Number(config.params?.page) || 1
    const perPage = Number(config.params?.per_page) || 20
    let list = [...mockNotifications].sort((a, b) => +dayjs(b.created_at) - +dayjs(a.created_at))
    if (String(config.params?.unread_only) === 'true') list = list.filter((n) => !n.is_read)
    const unreadCount = mockNotifications.filter((n) => !n.is_read).length
    const { items, pagination } = paginate(list, page, perPage)
    return ok({ items, pagination, unread_count: unreadCount })
  })

  mock.onPatch(/\/notifications\/read-all/).reply(() => {
    mockNotifications.forEach((n) => (n.is_read = true))
    return ok({})
  })

  mock.onPatch(/\/notifications\/\d+\/read/).reply((config) => {
    const id = Number(config.url!.match(/notifications\/(\d+)/)![1])
    const n = mockNotifications.find((x) => x.id === id)
    if (n) n.is_read = true
    return ok(n || {})
  })

  /* ------------------------------ feeds ------------------------------ */
  mock.onGet('/feeds/timeline').reply((config) => {
    const page = Number(config.params?.page) || 1
    const perPage = Number(config.params?.per_page) || 20
    const list = [...mockPosts].sort((a, b) => +dayjs(b.created_at) - +dayjs(a.created_at))
    const items = list.slice((page - 1) * perPage, page * perPage)
    return ok({
      items,
      source: 'cache',
      total: list.length,
      page,
      has_more: page * perPage < list.length,
    })
  })

  mock.onPost('/feeds/refresh').reply(() => ok({ refreshed: true }))

  // 兜底：未覆盖的接口返回 404，便于开发期发现漏配
  mock.onAny().reply((config) => {
    console.warn('[mock] 未拦截的请求:', config.method, config.url)
    return [404, { code: 404, error: `mock 未实现: ${config.method} ${config.url}`, request_id: 'mock-req' }]
  })
}
