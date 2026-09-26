<template>
  <section class="page" data-module="result">
    <header class="page-head">
      <div>
        <h2>检测结果管理</h2>
        <p class="page-desc">按检测值与检出限、判定上限的统一口径自动生成判定结论；没有判定规则的项目只能人工判定。</p>
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

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>结果编号</span>
        <input v-model="keyword" placeholder="按结果编号检索" />
      </label>
      <label class="filter-item">
        <span>结果状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <button class="link" type="button" @click="openDetail(row)">查看</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检测结果数据，可先登记检测结果</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测结果记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="noticeMessage" class="ok-text">{{ noticeMessage }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="closeDialogs">
      <div class="modal-card">
        <h3>登记检测结果</h3>
        <form @submit.prevent="submitCreate">
          <label class="form-item">
            <span>结果编号 *</span>
            <input v-model.trim="createForm.结果编号" placeholder="如 RESU-0009，重复编号会被拦下" />
          </label>
          <label class="form-item">
            <span>关联任务 *</span>
            <select v-model="createForm.关联任务" @change="syncCreateHint">
              <option value="" disabled>请选择检测任务</option>
              <option v-for="task in taskOptions" :key="String(task.任务编号)" :value="String(task.任务编号)">
                {{ task.任务编号 }}（{{ task.检测项目 }}）
              </option>
            </select>
          </label>
          <p v-if="createRule" class="rule-hint">
            统一口径：{{ createRule.检测项目 }}，单位 {{ createRule.计量单位 }}，检出限 {{ createRule.检出限 }}，判定上限 {{ createRule.判定上限 }}
          </p>
          <p v-else-if="createForm.关联任务" class="rule-hint warn">该项目未配置判定规则，提交后结论只能标记为「待人工判定」</p>
          <label class="form-item">
            <span>检测值 *</span>
            <input v-model.trim="createForm.检测值" placeholder="非负数值，未检出请填 0" />
          </label>
          <label class="form-item">
            <span>计量单位 *</span>
            <input v-model.trim="createForm.计量单位" placeholder="须与检测项目登记的单位一致" />
          </label>
          <label class="form-item">
            <span>录入人员</span>
            <input v-model.trim="createForm.录入人员" />
          </label>
          <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit">提交并自动判定</button>
            <button class="btn ghost" type="button" @click="closeDialogs">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="fillRow" class="modal-mask" @click.self="closeDialogs">
      <div class="modal-card">
        <h3>录入结果：{{ fillRow.结果编号 }}</h3>
        <form @submit.prevent="submitFill">
          <p class="rule-hint">关联任务 {{ fillRow.关联任务 }}（{{ fillRow.检测项目 ?? '—' }}）</p>
          <p v-if="fillRule" class="rule-hint">
            统一口径：单位 {{ fillRule.计量单位 }}，检出限 {{ fillRule.检出限 }}，判定上限 {{ fillRule.判定上限 }}
          </p>
          <p v-else class="rule-hint warn">该项目未配置判定规则，提交后结论只能标记为「待人工判定」</p>
          <label class="form-item">
            <span>检测值 *</span>
            <input v-model.trim="fillForm.检测值" placeholder="非负数值，未检出请填 0" />
          </label>
          <label class="form-item">
            <span>计量单位 *</span>
            <input v-model.trim="fillForm.计量单位" placeholder="须与检测项目登记的单位一致" />
          </label>
          <label class="form-item">
            <span>录入人员</span>
            <input v-model.trim="fillForm.录入人员" />
          </label>
          <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit">提交并自动判定</button>
            <button class="btn ghost" type="button" @click="closeDialogs">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="manualRow" class="modal-mask" @click.self="closeDialogs">
      <div class="modal-card">
        <h3>人工判定：{{ manualRow.结果编号 }}</h3>
        <form @submit.prevent="submitManual">
          <p class="rule-hint warn">「{{ manualRow.检测项目 }}」未配置判定规则，系统不自动生成结论，请人工填写。</p>
          <label class="form-item">
            <span>判定结论 *</span>
            <input v-model.trim="manualForm.判定结论" placeholder="如 阴性 / 阳性 / 合格 / 不合格" />
          </label>
          <p v-if="dialogError" class="error-text">{{ dialogError }}</p>
          <div class="modal-actions">
            <button class="btn primary" type="submit">提交人工判定</button>
            <button class="btn ghost" type="button" @click="closeDialogs">取消</button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="detailRow" class="modal-mask" @click.self="closeDialogs">
      <div class="modal-card">
        <h3>结果明细：{{ detailRow.结果编号 }}</h3>
        <dl class="detail-list">
          <template v-for="column in detailColumns" :key="column">
            <dt>{{ column }}</dt>
            <dd>{{ detailRow[column] ?? '—' }}</dd>
          </template>
        </dl>
        <div class="modal-actions">
          <button class="btn ghost" type="button" @click="closeDialogs">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/result'
const columns = ["结果编号", "关联任务", "检测项目", "检测值", "计量单位", "检出限", "判定上限", "判定结论", "录入人员", "结果状态"]
const detailColumns = [...columns]
const statuses = ["待录入", "已录入", "待复核", "已确认"]

interface StatCard {
  label: string
  value: number
}

interface TaskOption {
  任务编号: string
  检测项目: string
}

interface RuleItem {
  检测项目: string
  计量单位: string
  检出限: string
  判定上限: string
}

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<StatCard[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const taskOptions = ref<TaskOption[]>([])
const rules = ref<RuleItem[]>([])
const projectUnits = ref<Record<string, string>>({})

const createVisible = ref(false)
const createForm = ref({ 结果编号: '', 关联任务: '', 检测值: '', 计量单位: '', 录入人员: '' })
const fillRow = ref<Row | null>(null)
const fillForm = ref({ 检测值: '', 计量单位: '', 录入人员: '' })
const manualRow = ref<Row | null>(null)
const manualForm = ref({ 判定结论: '' })
const detailRow = ref<Row | null>(null)
const dialogError = ref('')

const createProject = computed(() => {
  const task = taskOptions.value.find((item) => item.任务编号 === createForm.value.关联任务)
  return task?.检测项目 ?? ''
})
const createRule = computed(() => rules.value.find((item) => item.检测项目 === createProject.value) ?? null)
const fillRule = computed(() => rules.value.find((item) => item.检测项目 === String(fillRow.value?.检测项目 ?? '')) ?? null)

function rowActions(row: Row): string[] {
  const status = String(row.status ?? '')
  if (status === '待录入') return ['录入结果']
  if (status === '已录入') return row.manual_required ? ['人工判定'] : ['提交复核']
  if (status === '待复核') return ['确认结果']
  return []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.value = { 结果编号: '', 关联任务: '', 检测值: '', 计量单位: '', 录入人员: '' }
  dialogError.value = ''
  createVisible.value = true
}

function syncCreateHint() {
  // 选中任务后按项目档案预填计量单位，录入人仍要以统一口径提示为准。
  createForm.value.计量单位 = projectUnits.value[createProject.value] ?? ''
}

function openDetail(row: Row) {
  detailRow.value = row
  dialogError.value = ''
}

function closeDialogs() {
  createVisible.value = false
  fillRow.value = null
  manualRow.value = null
  detailRow.value = null
  dialogError.value = ''
}

async function readAction(response: Response): Promise<{ ok: boolean; message: string }> {
  const payload = (await response.json()) as { ok?: boolean; message?: string }
  return { ok: Boolean(payload.ok), message: payload.message ?? '操作未生效' }
}

async function submitCreate() {
  dialogError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm.value } }),
    })
    const result = await readAction(response)
    if (!result.ok) {
      dialogError.value = result.message
      return
    }
    closeDialogs()
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '检测结果登记失败'
  }
}

async function submitFill() {
  if (!fillRow.value) return
  dialogError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${fillRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '录入结果', ...fillForm.value } }),
    })
    const result = await readAction(response)
    if (!result.ok) {
      dialogError.value = result.message
      return
    }
    closeDialogs()
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '检测结果录入失败'
  }
}

async function submitManual() {
  if (!manualRow.value) return
  dialogError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${manualRow.value.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '人工判定', ...manualForm.value } }),
    })
    const result = await readAction(response)
    if (!result.ok) {
      dialogError.value = result.message
      return
    }
    closeDialogs()
    noticeMessage.value = result.message
    await reload()
  } catch (error) {
    dialogError.value = error instanceof Error ? error.message : '人工判定提交失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  if (action === '录入结果') {
    fillRow.value = row
    fillForm.value = { 检测值: '', 计量单位: projectUnits.value[String(row.检测项目 ?? '')] ?? '', 录入人员: '' }
    dialogError.value = ''
    return
  }
  if (action === '人工判定') {
    manualRow.value = row
    manualForm.value = { 判定结论: '' }
    dialogError.value = ''
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readAction(response)
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    noticeMessage.value = result.message
    // 确认结论后回到结果列表复核：列表与统计卡片一起刷新，口径保持一致。
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测结果操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('检测结果列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const statPayload = await statsResponse.json()
      stats.value = statPayload.items ?? []
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测结果列表读取失败'
  }
}

async function loadRefs() {
  try {
    const [taskResponse, projectResponse, ruleResponse] = await Promise.all([
      request('/api/task?size=200'),
      request('/api/project?size=200'),
      request(`${ENDPOINT}/rules`),
    ])
    if (taskResponse.ok) {
      const payload = await taskResponse.json()
      taskOptions.value = (payload.items ?? []).map((item: Row) => ({
        任务编号: String(item.任务编号 ?? ''),
        检测项目: String(item.检测项目 ?? ''),
      }))
    }
    if (projectResponse.ok) {
      const payload = await projectResponse.json()
      const units: Record<string, string> = {}
      for (const item of payload.items ?? []) {
        units[String(item.项目名称 ?? '')] = String(item.计量单位 ?? '')
      }
      projectUnits.value = units
    }
    if (ruleResponse.ok) {
      const payload = await ruleResponse.json()
      rules.value = payload.items ?? []
    }
  } catch {
    // 参考数据加载失败不阻塞列表，登记时再按后端校验提示处理。
  }
}

onMounted(() => {
  void reload()
  void loadRefs()
})
</script>
