<template>
  <section class="page" data-module="cleaning-detail">
    <header class="page-head">
      <div>
        <h2>清洗任务详情</h2>
        <p class="page-desc">查看任务的区域、班组、计划与实际完成情况，并可继续执行排期、开工与取消动作。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回清洗列表</button>
      </div>
    </header>

    <article v-if="entry" class="detail-card">
      <div class="detail-head">
        <div>
          <h3>{{ entry['任务编号'] }}</h3>
          <span class="status-chip">{{ entry.status ?? entry['任务状态'] }}</span>
          <span v-if="overdue" class="tag tag-overdue">计划日期超期</span>
        </div>
      </div>
      <dl class="detail-grid">
        <div v-for="column in columns" :key="column" class="detail-item">
          <dt>{{ column }}</dt>
          <dd>
            <template v-if="column === '实际完成日' && missingDone">
              <span class="tag tag-missing">未填实际完成日</span>
            </template>
            <template v-else>{{ entry[column] ?? '—' }}</template>
          </dd>
        </div>
      </dl>

      <div class="detail-actions">
        <button
          v-for="action in actions"
          :key="action"
          class="btn"
          :class="{ primary: action !== '取消任务' }"
          type="button"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>
      <p v-if="message" class="result-text">{{ message }}</p>
    </article>

    <p v-else-if="!errorMessage" class="muted-text">正在加载清洗任务…</p>
    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, string | number | null>

const ENDPOINT = '/api/cleaning'
const LIST_QUERY_KEY = 'cleaning:list-query'
const columns = ['任务编号', '清洗区域', '计划日期', '实际完成日', '用水量', '作业班组', '清洗方式', '任务状态']
const actions = ['确认排期', '开始清洗', '取消任务']

const route = useRoute()
const router = useRouter()

const entry = ref<Entry | null>(null)
const errorMessage = ref('')
const message = ref('')

const overdue = computed(() => {
  if (!entry.value) return false
  const status = String(entry.value.status ?? '')
  if (status === '已完成' || status === '已取消') return false
  const plan = String(entry.value['计划日期'] ?? '').slice(0, 10)
  if (!plan) return false
  return plan < new Date().toISOString().slice(0, 10)
})

const missingDone = computed(() => !String(entry.value?.['实际完成日'] ?? '').trim())

async function load() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    if (!response.ok) throw new Error('清洗任务详情读取失败')
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '清洗任务详情读取失败'
  }
}

async function runAction(action: string) {
  message.value = ''
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) throw new Error('组件清洗动作未生效，请稍后重试')
    const payload = await response.json().catch(() => null)
    if (payload && payload.ok === false) throw new Error(payload.message || '组件清洗动作未生效')
    message.value = payload?.message ?? '操作已生效'
    await load()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '组件清洗操作失败'
  }
}

function goBack() {
  // 列表把完整筛选与页码放在 from 里；优先回退历史（浏览器后退天然还原列表状态），
  // 没有历史（例如刷新后）时用 from 或缓存兜底。
  if (window.history.state?.back) {
    router.back()
    return
  }
  const from = typeof route.query.from === 'string' ? route.query.from : ''
  void router.push(from || sessionStorage.getItem(LIST_QUERY_KEY) || '/cleaning')
}

onMounted(load)
</script>

<style scoped>
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
}
.detail-head h3 {
  display: inline-block;
  margin: 0 10px 0 0;
}
.status-chip {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 32px;
  margin: 16px 0;
}
.detail-item dt {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 2px;
}
.detail-item dd {
  margin: 0;
  font-size: 14px;
}
.detail-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}
.tag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 16px;
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
.result-text {
  color: #1d4ed8;
  font-size: 13px;
}
.muted-text {
  color: var(--muted);
}
</style>
