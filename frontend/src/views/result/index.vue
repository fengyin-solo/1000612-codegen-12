<template>
  <section class="page" data-module="result">
    <header class="page-head">
      <div>
        <h2>检测结果管理</h2>
        <p class="page-desc">维护检测结果，围绕结果编号、关联任务、检测值、计量单位做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测结果</button>
        <button class="btn" type="button" @click="exportRows">导出检测结果清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showCreate" class="create-panel" @submit.prevent="submitCreate">
      <label v-for="field in createFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="createForm[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit">提交录入</button>
      <button class="btn ghost" type="button" @click="closeCreate">取消</button>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
            <span v-if="column === '判定结论'" class="tag" :class="conclusionClass(row[column])">
              {{ row[column] ?? '—' }}
            </span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无检测结果数据，可先登记检测结果</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测结果记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/result'
const columns = ["结果编号", "关联任务", "检测值", "计量单位", "检出限", "判定上限", "判定结论", "录入人员", "结果状态"]
const actions = ["录入结果", "提交复核", "确认结果"]
const createFields = ["结果编号", "关联任务", "检测值", "计量单位", "录入人员"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const stats = ref([{"label": "待录入结果", "value": 0}, {"label": "待复核结果", "value": 0}, {"label": "不合格结果数", "value": 0}])
const showCreate = ref(false)
const createForm = ref<Record<string, string>>({})

function conclusionClass(value: Row[string]) {
  if (value === '超出上限') return 'tag-danger'
  if (value === '待人工判定') return 'tag-warn'
  return 'tag-ok'
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = {}
  showCreate.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
}

function closeCreate() {
  showCreate.value = false
  createForm.value = {}
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '检测结果录入被拦下'
      return
    }
    noticeMessage.value = payload.message || '检测结果已登记'
    closeCreate()
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测结果登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!payload.ok) {
      errorMessage.value = payload.message || '检测结果动作未生效'
      return
    }
    noticeMessage.value = payload.message || `检测结果已${action}`
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测结果操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    stats.value = payload.items ?? stats.value
  } catch {
    // 统计卡片读取失败时保留上一次数据，不打断列表操作
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  for (const [field, text] of Object.entries(filters.value)) {
    const keyword = String(text ?? '').trim()
    if (!keyword) continue
    // 结果编号对应后端的 keyword 参数，其余字段按中文名透传
    query.set(field === '结果编号' ? 'keyword' : field, keyword)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('检测结果列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测结果列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>
