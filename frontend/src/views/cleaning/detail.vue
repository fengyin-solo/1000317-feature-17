<template>
  <section class="page" data-module="cleaning-detail">
    <header class="page-head">
      <div>
        <h2>清洗任务详情</h2>
        <p class="page-desc">查看单条清洗任务的排期与完成情况，返回列表后筛选条件与页码保持不动。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <table v-if="entry" class="data-table detail-table">
      <tbody>
        <tr v-for="field in fields" :key="field">
          <th>{{ field }}</th>
          <td>{{ entry[field] ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const fields = ["任务编号", "清洗区域", "计划日期", "实际完成日", "用水量", "作业班组", "清洗方式", "任务状态"]

const route = useRoute()
const router = useRouter()

const entry = ref<Row | null>(null)
const errorMessage = ref('')

function goBack() {
  // 从列表跳进详情时回退到带筛选参数的列表地址；直接打开详情时回列表首页
  if (window.history.state?.back) {
    router.back()
  } else {
    void router.push({ name: 'cleaning' })
  }
}

onMounted(async () => {
  try {
    const response = await request(`/api/cleaning/${route.params.id}`)
    if (!response.ok) {
      throw new Error('清洗任务详情读取失败')
    }
    entry.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '清洗任务详情读取失败'
  }
})
</script>
