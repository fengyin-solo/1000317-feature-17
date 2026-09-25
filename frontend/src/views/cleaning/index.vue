<template>
  <section class="page" data-module="cleaning">
    <header class="page-head">
      <div>
        <h2>组件清洗管理</h2>
        <p class="page-desc">维护清洗任务，围绕任务编号、清洗区域、计划日期、实际完成日做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记清洗任务</button>
        <button class="btn" type="button" @click="exportRows">导出组件清洗清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}<small v-if="item.unit" class="stat-unit">{{ item.unit }}</small></strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>任务编号</span>
        <input v-model="form.keyword" placeholder="按任务编号检索" />
      </label>
      <label class="filter-item">
        <span>清洗区域</span>
        <input v-model="form.area" list="cleaning-area-options" placeholder="按清洗区域筛选" />
        <datalist id="cleaning-area-options">
          <option v-for="area in areaOptions" :key="area" :value="area" />
        </datalist>
      </label>
      <label class="filter-item">
        <span>作业班组</span>
        <input v-model="form.team" list="cleaning-team-options" placeholder="按作业班组筛选" />
        <datalist id="cleaning-team-options">
          <option v-for="team in teamOptions" :value="team" :key="team" />
        </datalist>
      </label>
      <label class="filter-item">
        <span>任务状态</span>
        <select v-model="form.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>计划月份</span>
        <input v-model="form.month" type="month" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-overdue': row.overdue }">
          <td>
            <RouterLink class="link" :to="detailLink(row)">{{ row['任务编号'] }}</RouterLink>
            <span v-if="row.overdue" class="tag tag-overdue">超期</span>
          </td>
          <td>{{ row['清洗区域'] ?? '—' }}</td>
          <td>{{ row['计划日期'] ?? '—' }}</td>
          <td>
            <span v-if="row['实际完成日']">{{ row['实际完成日'] }}</span>
            <span v-else class="tag tag-missing">未填实际完成日</span>
          </td>
          <td>{{ row['用水量'] ?? '—' }}</td>
          <td>{{ row['作业班组'] ?? '—' }}</td>
          <td>{{ row['清洗方式'] ?? '—' }}</td>
          <td>{{ row['任务状态'] ?? row.status ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">当前筛选条件下暂无清洗任务，可调整区域、班组或月份后重试</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条组件清洗记录，第 {{ page }} / {{ totalPages }} 页</span>
      <span class="pager">
        <button class="btn" type="button" :disabled="page <= 1" @click="goPage(page - 1)">上一页</button>
        <button class="btn" type="button" :disabled="page >= totalPages" @click="goPage(page + 1)">下一页</button>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

type QueryState = {
  keyword: string
  area: string
  team: string
  status: string
  month: string
  page: number
}

const ENDPOINT = '/api/cleaning'
const LIST_QUERY_KEY = 'cleaning:list-query'
const columns = ['任务编号', '清洗区域', '计划日期', '实际完成日', '用水量', '作业班组', '清洗方式', '任务状态']
const actions = ['确认排期', '开始清洗', '取消任务']
const statuses = ['待排期', '已排期', '清洗中', '已完成', '已取消']
const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const errorMessage = ref('')
const stats = ref<{ pending: number; cleaning: number; water: number }>({ pending: 0, cleaning: 0, water: 0 })

const currentMonth = new Date().toISOString().slice(0, 7)

// 输入框绑定的是本地表单；真正生效的筛选以 URL query 为准（刷新/前进后退都能还原）。
const form = reactive({ keyword: '', area: '', team: '', status: '', month: currentMonth })

const areaOptions = computed(() => collectOptions('清洗区域'))
const teamOptions = computed(() => collectOptions('作业班组'))
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const statCards = computed(() => [
  { label: '待排期清洗', value: stats.value.pending, unit: '' },
  { label: '清洗中任务', value: stats.value.cleaning, unit: '' },
  { label: `${form.month || currentMonth} 用水量`, value: stats.value.water, unit: '吨' },
])

function collectOptions(field: string): string[] {
  const values = new Set(rows.value.map((row) => String(row[field] ?? '')).filter(Boolean))
  return [...values].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
}

function readRouteQuery(): QueryState {
  const q = route.query
  return {
    keyword: String(q.keyword ?? ''),
    area: String(q.area ?? ''),
    team: String(q.team ?? ''),
    status: String(q.status ?? ''),
    month: q.month === undefined ? currentMonth : String(q.month),
    page: Math.max(1, Number(q.page) || 1),
  }
}

function syncForm() {
  const state = readRouteQuery()
  form.keyword = state.keyword
  form.area = state.area
  form.team = state.team
  form.status = state.status
  form.month = state.month
}

function buildQuery(state: Partial<QueryState>, withPage = true): Record<string, string> {
  const params: Record<string, string> = {}
  if (state.keyword) params.keyword = state.keyword as string
  if (state.area) params.area = state.area as string
  if (state.team) params.team = state.team as string
  if (state.status) params.status = state.status as string
  if (state.month) params.month = state.month as string
  if (withPage && state.page && Number(state.page) > 1) params.page = String(state.page)
  return params
}

async function reload() {
  syncForm()
  const state = readRouteQuery()
  errorMessage.value = ''
  const listParams = new URLSearchParams({ ...buildQuery(state), size: String(PAGE_SIZE) }).toString()
  const statParams = new URLSearchParams(
    buildQuery({ keyword: '', area: state.area, team: state.team, status: '', month: state.month, page: 1 }, false),
  ).toString()

  try {
    const [listResponse, statResponse] = await Promise.all([
      request(`${ENDPOINT}?${listParams}`),
      request(`${ENDPOINT}/stats?${statParams}`),
    ])
    if (!listResponse.ok) throw new Error('清洗任务列表读取失败')
    if (!statResponse.ok) throw new Error('清洗统计卡片读取失败')
    const payload = await listResponse.json()
    const statPayload = await statResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    stats.value = {
      pending: Number(statPayload.pending ?? 0),
      cleaning: Number(statPayload.cleaning ?? 0),
      water: Number(statPayload.water ?? 0),
    }

    // 取消等动作可能让当前页变空，自动回退到最后一个有效页而不是停在空白页。
    const lastPage = Math.max(1, Math.ceil(total.value / PAGE_SIZE))
    if (state.page > lastPage) {
      await replacePage(lastPage)
      return
    }
    page.value = state.page
    sessionStorage.setItem(LIST_QUERY_KEY, route.fullPath)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '组件清洗列表读取失败'
  }
}

function applyFilters() {
  void router.replace({ query: buildQuery({ ...form, page: 1 }) })
}

function resetFilters() {
  void router.replace({ query: buildQuery({ keyword: '', area: '', team: '', status: '', month: currentMonth, page: 1 }) })
}

function goPage(target: number) {
  const state = readRouteQuery()
  void router.replace({ query: buildQuery({ ...state, page: Math.min(Math.max(1, target), totalPages.value) }) })
}

async function replacePage(target: number) {
  const state = readRouteQuery()
  await router.replace({ query: buildQuery({ ...state, page: target }) })
}

function exportRows() {
  const state = readRouteQuery()
  const params = new URLSearchParams(buildQuery(state, false)).toString()
  window.open(`${ENDPOINT}/export${params ? `?${params}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '清洗任务登记入口尚未接入审批流'
}

function detailLink(row: Row) {
  // 把当前列表完整状态带进详情页，返回时按它还原筛选与页码。
  return { path: `/cleaning/${row.id}`, query: { from: route.fullPath } }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) throw new Error('组件清洗动作未生效，请稍后重试')
    const payload = await response.json().catch(() => null)
    if (payload && payload.ok === false) throw new Error(payload.message || '组件清洗动作未生效')
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '组件清洗操作失败'
  }
}

// 离开列表（含进入任务详情）前记住当前筛选与页码，详情页返回时可兜底恢复。
onBeforeRouteLeave((to) => {
  if (to.path.startsWith('/cleaning/')) {
    sessionStorage.setItem(LIST_QUERY_KEY, route.fullPath)
  }
  return true
})

watch(() => route.query, () => void reload(), { deep: true })

void reload()
</script>

<style scoped>
.stat-unit {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 400;
  color: var(--muted);
}
.tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 16px;
  white-space: nowrap;
}
.tag-overdue {
  background: #fef3f2;
  color: #b42318;
  border: 1px solid #fecdca;
}
.tag-missing {
  background: #fffaeb;
  color: #b54708;
  border: 1px solid #fedf89;
}
.row-overdue {
  background: #fffbfa;
}
.pager {
  display: inline-flex;
  gap: 6px;
}
.pager .btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
