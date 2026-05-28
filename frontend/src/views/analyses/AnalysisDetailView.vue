<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAnalysesStore } from '@/stores/analyses'
import ParameterHistoryChart from '@/components/analyses/ParameterHistoryChart.vue'
import type { AnalysisValue } from '@/api/analyses'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useAnalysesStore()

const recordId = Number(route.params.id)
const chartDialog = ref(false)
const chartValue = ref<AnalysisValue | null>(null)
const deleteDialog = ref(false)

onMounted(async () => {
  await store.fetchRecord(recordId)
})

const record = computed(() => store.currentRecord)

function abnormalColor(v: AnalysisValue): string | undefined {
  if (v.abnormal_type === 'unknown') return undefined
  if (v.is_abnormal) return 'red'
  if (isCloseToBoundary(v)) return 'orange'
  return 'green'
}

function abnormalIcon(v: AnalysisValue): string {
  if (v.abnormal_type === 'unknown') return 'mdi-help-circle-outline'
  if (v.is_abnormal) return v.abnormal_type === 'high' ? 'mdi-arrow-up-bold' : 'mdi-arrow-down-bold'
  return 'mdi-check-circle-outline'
}

function isCloseToBoundary(v: AnalysisValue): boolean {
  if (v.abnormal_type !== 'normal') return false
  const value = Number(v.value.replace(',', '.'))
  if (Number.isNaN(value)) return false
  const min = v.reference_min ? Number(v.reference_min.replace(',', '.')) : null
  const max = v.reference_max ? Number(v.reference_max.replace(',', '.')) : null
  if (min !== null && value <= min * 1.05) return true
  if (max !== null && value >= max * 0.95) return true
  return false
}

function openChart(v: AnalysisValue): void {
  if (!v.parameter_code) return
  chartValue.value = v
  chartDialog.value = true
}

async function confirmDelete(): Promise<void> {
  if (!record.value) return
  await store.deleteRecord(record.value.id)
  router.push({ name: 'analyses' })
}

function askIvan(): void {
  if (!record.value) return
  router.push({
    name: 'ai-chat',
    query: {
      analysis_id: String(record.value.id),
      prefill: t('ai.prefill_question_analysis'),
    },
  })
}
</script>

<template>
  <v-container v-if="record" fluid>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h4">{{ t('analyses.detail.title') }} {{ record.analysis_date }}</h1>
      <v-spacer />
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-robot-happy"
        @click="askIvan"
      >
        {{ t('analyses.detail.ask_ivan') }}
      </v-btn>
      <v-btn variant="text" color="error" prepend-icon="mdi-delete" @click="deleteDialog = true">
        {{ t('analyses.detail.delete') }}
      </v-btn>
    </div>

    <v-card class="pa-4 mb-4">
      <p><strong>{{ t('analyses.detail.lab') }}:</strong> {{ record.lab_name ?? '—' }}</p>
      <p><strong>{{ t('analyses.detail.doctor') }}:</strong> {{ record.doctor_referral ?? '—' }}</p>
      <p v-if="record.notes"><strong>{{ t('analyses.detail.notes') }}:</strong> {{ record.notes }}</p>
    </v-card>

    <v-card class="pa-0">
      <v-table density="comfortable">
        <thead>
          <tr>
            <th></th>
            <th>{{ t('analyses.detail.parameter') }}</th>
            <th>{{ t('analyses.detail.value') }}</th>
            <th>{{ t('analyses.detail.unit') }}</th>
            <th>{{ t('analyses.detail.reference') }}</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in record.values" :key="v.id">
            <td>
              <v-icon :icon="abnormalIcon(v)" :color="abnormalColor(v)" />
            </td>
            <td>{{ v.parameter_name }}</td>
            <td>
              <span :class="{ 'text-red font-weight-bold': v.is_abnormal }">{{ v.value }}</span>
            </td>
            <td>{{ v.unit }}</td>
            <td>
              <span v-if="v.reference_min || v.reference_max">
                {{ v.reference_min ?? '—' }} – {{ v.reference_max ?? '—' }}
              </span>
              <span v-else class="text-disabled">—</span>
            </td>
            <td>
              <v-btn
                v-if="v.parameter_code"
                variant="text"
                size="small"
                prepend-icon="mdi-chart-line"
                @click="openChart(v)"
              >
                {{ t('analyses.detail.show_history') }}
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-dialog v-model="chartDialog" max-width="720">
      <v-card class="pa-4">
        <ParameterHistoryChart
          v-if="chartValue?.parameter_code"
          :parameter-code="chartValue.parameter_code"
          :parameter-name="chartValue.parameter_name"
          :unit="chartValue.unit"
        />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="chartDialog = false">{{ t('common.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="400">
      <v-card class="pa-4">
        <v-card-title>{{ t('analyses.detail.delete_confirm_title') }}</v-card-title>
        <v-card-text>{{ t('analyses.detail.delete_confirm_text') }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteDialog = false">{{ t('common.cancel') }}</v-btn>
          <v-btn color="error" @click="confirmDelete">{{ t('analyses.detail.delete') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
  <v-container v-else>
    <p>{{ t('analyses.detail.loading') }}</p>
  </v-container>
</template>
