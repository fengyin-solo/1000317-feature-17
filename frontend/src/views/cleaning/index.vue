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
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>任务编号</span>
        <input v-model="filters.keyword" placeholder="按任务编号检索" />
      </label>
      <label class="filter-item">
        <span>清洗区域</span>
        <input v-model="filters.area" placeholder="按清洗区域检索" />
      </label>
      <label class="filter-item">
        <span>作业班组</span>
        <input v-model="filters.team" placeholder="按作业班组检索" />
      </label>
      <label class="filter-item">
        <span>计划月份</span>
        <input v-model="filters.month" type="month" />
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
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '计划日期'">
              {{ row[column] ?? '—' }}
              <span v-if="isOverdue(row)" class="tag danger">已超期</span>
            </template>
            <template v-else-if="column === '实际完成日'">
              <span v-if="isFinishDateMissing(row)" class="tag warn">完成日缺失</span>
              <template v-else>{{ row[column] ?? '—' }}</template>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <RouterLink class="link" :to="{ name: 'cleaning-detail', params: { id: row.id } }">
              详情
            </RouterLink>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无组件清洗数据，可先登记清洗任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条组件清洗记录</span>
      <div class="pager">
        <button class="btn ghost" type="button" :disabled="page <= 1" @click="goPage(-1)">上一页</button>
        <span>第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn ghost" type="button" :disabled="page >= totalPages" @click="goPage(1)">下一页</button>
      </div>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: number }

const ENDPOINT = '/api/cleaning'
const PAGE_SIZE = 10
const columns = ["任务编号", "清洗区域", "计划日期", "实际完成日", "用水量", "作业班组", "清洗方式", "任务状态"]
const actions = ["确认排期", "开始清洗", "取消任务"]
const CLOSED_STATUSES = ["已完成", "已取消"]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const page = ref(1)
const errorMessage = ref('')
const stats = ref<StatCard[]>([
  { label: '待排期清洗', value: 0 },
  { label: '清洗中任务', value: 0 },
  { label: '本月用水量', value: 0 },
])
const filters = reactive({ keyword: '', area: '', team: '', month: '' })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function readQuery() {
  filters.keyword = String(route.query.keyword ?? '')
  filters.area = String(route.query.area ?? '')
  filters.team = String(route.query.team ?? '')
  filters.month = String(route.query.month ?? '')
  page.value = Math.max(1, Number(route.query.page) || 1)
}

function syncQuery() {
  const query: Record<string, string> = {}
  if (filters.keyword) query.keyword = filters.keyword
  if (filters.area) query.area = filters.area
  if (filters.team) query.team = filters.team
  if (filters.month) query.month = filters.month
  if (page.value > 1) query.page = String(page.value)
  const keys = Object.keys(query)
  const unchanged =
    keys.length === Object.keys(route.query).length &&
    keys.every((key) => String(route.query[key] ?? '') === query[key])
  if (unchanged) {
    // 条件没变化时 replace 不会触发 watch，手动刷新一次保证查询按钮始终有效
    void reload()
    return
  }
  void router.replace({ query })
}

function applyFilters() {
  page.value = 1
  syncQuery()
}

function resetFilters() {
  filters.keyword = ''
  filters.area = ''
  filters.team = ''
  filters.month = ''
  page.value = 1
  syncQuery()
}

function goPage(delta: number) {
  const next = page.value + delta
  if (next < 1 || next > totalPages.value) return
  page.value = next
  syncQuery()
}

function isOverdue(row: Row) {
  const status = String(row['任务状态'] ?? '')
  if (CLOSED_STATUSES.includes(status)) return false
  const plan = new Date(String(row['计划日期'] ?? ''))
  if (Number.isNaN(plan.getTime())) return false
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return plan < today
}

function isFinishDateMissing(row: Row) {
  return String(row['任务状态'] ?? '') === '已完成' && !row['实际完成日']
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '清洗任务登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('组件清洗动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '组件清洗操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.area) query.set('area', filters.area)
  if (filters.team) query.set('team', filters.team)
  if (filters.month) query.set('month', filters.month)
  query.set('page', String(page.value))
  query.set('size', String(PAGE_SIZE))
  try {
    const [response, statPayload] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      fetchJson<{ cards: StatCard[] }>(`${ENDPOINT}/stats`),
    ])
    if (!response.ok) {
      throw new Error('清洗任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    stats.value = statPayload.cards ?? stats.value
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '组件清洗列表读取失败'
  }
}

// query 变化（含浏览器前进/后退）时恢复筛选与页码再刷新；replace 与当前一致时不会重复触发
watch(
  () => route.query,
  () => {
    readQuery()
    void reload()
  },
)

onMounted(() => {
  readQuery()
  void reload()
})
</script>
