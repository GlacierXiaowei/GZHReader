import { Command, type Child } from '@tauri-apps/plugin-shell'

type Pending = {
  resolve: (value: any) => void
  reject: (reason?: any) => void
  timer: ReturnType<typeof setTimeout>
}
type Listener = (payload: any) => void

class CoreClient {
  private child: Child | null = null
  private id = 0
  private pending = new Map<number, Pending>()
  private listeners = new Map<string, Set<Listener>>()
  private ready: Promise<void> | null = null
  private mock = false
  private stopping = false
  private buffer = ''
  private restartCount = 0

  async start() {
    if (this.ready) return this.ready
    this.stopping = false
    this.ready = this.spawn()
    return this.ready
  }

  private async spawn() {
    try {
      const command = Command.sidecar('binaries/gzhreader-core')
      command.stdout.on('data', chunk => this.receive(String(chunk)))
      command.stderr.on('data', line => console.warn('[core]', line))
      command.on('error', error => this.handleExit(new Error(String(error))))
      command.on('close', () => this.handleExit(new Error('本地核心已经停止')))
      this.child = await command.spawn()
      this.restartCount = 0
    } catch (error) {
      this.ready = null
      if (!this.isTauri()) {
        console.warn('Sidecar unavailable; using preview data', error)
        this.mock = true
        return
      }
      throw new Error('本地核心暂时无法启动，请重新打开应用')
    }
  }

  private isTauri() {
    return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  }

  on(event: string, listener: Listener) {
    const set = this.listeners.get(event) ?? new Set<Listener>()
    set.add(listener)
    this.listeners.set(event, set)
    return () => set.delete(listener)
  }

  private receive(chunk: string) {
    this.buffer += chunk
    const lines = this.buffer.split(/\r?\n/)
    this.buffer = lines.pop() ?? ''
    for (const line of lines) this.parse(line)
    if (this.buffer.trim()) {
      try {
        JSON.parse(this.buffer)
        const complete = this.buffer
        this.buffer = ''
        this.parse(complete)
      } catch { /* wait for the rest of the JSON line */ }
    }
  }

  private parse(raw: string) {
    if (!raw.trim()) return
    try {
      const message = JSON.parse(raw)
      if (message.event) this.listeners.get(message.event)?.forEach(fn => fn(message.payload))
      if (message.id != null) {
        const pending = this.pending.get(message.id)
        if (!pending) return
        clearTimeout(pending.timer)
        this.pending.delete(message.id)
        message.error ? pending.reject(new Error(message.error.message)) : pending.resolve(message.result)
      }
    } catch (error) {
      console.warn('Invalid core message', raw, error)
    }
  }

  private handleExit(error: Error) {
    this.child = null
    this.ready = null
    this.buffer = ''
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer)
      pending.reject(error)
    }
    this.pending.clear()
    if (this.stopping || this.mock || this.restartCount >= 3) return
    this.restartCount += 1
    this.listeners.get('core.error')?.forEach(fn => fn({ message: '本地核心正在恢复连接' }))
    setTimeout(() => this.start().catch(() => undefined), 800 * this.restartCount)
  }

  async call<T = any>(method: string, params: Record<string, any> = {}): Promise<T> {
    await this.start()
    if (this.mock) return mockCall(method, params) as T
    if (!this.child) {
      this.ready = null
      await this.start()
    }
    if (!this.child) throw new Error('本地核心暂时无法启动')
    const id = ++this.id
    const promise = new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        reject(new Error('操作等待时间较长，请稍后查看结果'))
      }, 120_000)
      this.pending.set(id, { resolve, reject, timer })
    })
    await this.child.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
    return promise
  }

  async stop() {
    this.stopping = true
    try {
      if (this.child) await this.call('core.shutdown')
    } catch { /* process may already be gone */ }
  }
}

const sampleArticles = [
  { id: 1, source_id: 'demo-1', source_name: '少数派', source_avatar: '', title: '把信息整理成真正能回看的知识', published_at: new Date().toISOString(), summary: '文章讨论了信息收集与知识整理的差别。与其不断增加订阅，不如建立稳定的筛选、摘要和回顾节奏。', takeaway: '好的阅读系统不是收集更多，而是留下真正重要的内容。', key_points: ['先筛选，再阅读', '摘要服务于回顾', '定期清理低价值来源'], tags: ['阅读', '知识管理'], content: '这是一篇用于桌面界面预览的示例文章。', url: 'https://mp.weixin.qq.com/', is_read: 0, summary_status: 'done' },
  { id: 2, source_id: 'demo-2', source_name: '产品沉思录', source_avatar: '', title: '如何保持长期而稳定的输入', published_at: new Date(Date.now() - 3600000).toISOString(), summary: '稳定的内容输入依赖清楚的关注范围和低摩擦的回顾工具，而不是依赖意志力。', takeaway: '让系统承担重复工作，把注意力留给判断。', key_points: ['减少重复操作', '保持固定节奏'], tags: ['产品', '方法'], content: '示例正文。', url: 'https://mp.weixin.qq.com/', is_read: 0, summary_status: 'done' }
]
const mockState: any = {
  settings: { refresh_minutes: 60, refresh_paused: false, briefing_enabled: true, briefing_time: '21:30', auto_summary: true, autostart: true, theme: 'light', next_refresh_at: new Date(Date.now() + 3600000).toISOString(), ai: { base_url: '', model: '', has_api_key: false, enabled: true } },
  sources: [{ id: 'demo-1', name: '少数派', intro: '高效工作与品质生活', avatar: '', enabled: 1, status: 'active', last_success_at: new Date().toISOString() }, { id: 'demo-2', name: '产品沉思录', intro: '产品与个人成长', avatar: '', enabled: 1, status: 'active', last_success_at: new Date().toISOString() }],
  articles: sampleArticles,
  briefings: [], connection: { state: 'disconnected', message: '需要连接微信读书', reconnect_required: true }, scheduler: { running: true }
}
async function mockCall(method: string, params: any) {
  await new Promise(resolve => setTimeout(resolve, 160))
  if (method === 'app.bootstrap') return { dashboard: { today_count: 2, unread_count: 2, today_briefing: null }, ...mockState }
  if (method === 'subscriptions.list') return mockState.sources
  if (method === 'articles.list') return mockState.articles.filter((article: any) => !params.unread_only || !article.is_read)
  if (method === 'articles.get') return mockState.articles.find((article: any) => article.id === params.article_id)
  if (method === 'briefings.list') return mockState.briefings
  if (method === 'settings.get') return mockState.settings
  if (method === 'settings.update') { mockState.settings = { ...mockState.settings, ...params.settings }; return mockState.settings }
  if (method === 'subscriptions.resolve_link') return { id: 'MP_WXS_preview', name: '识别到的公众号', intro: '请确认后开始关注', avatar: '', sample_url: params.url, status: 'active' }
  if (method === 'subscriptions.add') { mockState.sources.unshift({ ...params.source, enabled: 1 }); return params.source }
  if (method === 'briefings.generate') { const briefing = { day: new Date().toISOString().slice(0,10), overview: '今天的内容主要围绕阅读方法和产品思考。', article_count: 2, markdown: '# 每日简报', file_path: 'Documents/GZHReader/Briefings' }; mockState.briefings.unshift(briefing); return briefing }
  return { ok: true, accepted: true, message: '操作已完成' }
}

export const core = new CoreClient()
