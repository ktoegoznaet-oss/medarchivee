<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Line } from 'vue-chartjs'
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
} from 'chart.js'
import annotationPlugin from 'chartjs-plugin-annotation'
import dayjs from 'dayjs'
import { analysesApi, type AnalysisHistoryPoint } from '@/api/analyses'

ChartJS.register(
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
  annotationPlugin,
)

const props = defineProps<{
  parameterCode: string
  parameterName: string
  unit: string
}>()

const range = ref<'6m' | '1y' | '5y' | 'all'>('1y')
const points = ref<AnalysisHistoryPoint[]>([])
const loading = ref(false)

function dateFromForRange(): string | undefined {
  if (range.value === 'all') return undefined
  const months = range.value === '6m' ? 6 : range.value === '1y' ? 12 : 60
  return dayjs().subtract(months, 'month').format('YYYY-MM-DD')
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const { data } = await analysesApi.history(props.parameterCode, dateFromForRange())
    points.value = data.points
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(range, load)

const refMin = computed<number | null>(() => {
  const v = points.value.find((p) => p.reference_min)?.reference_min
  return v ? Number(v.replace(',', '.')) : null
})

const refMax = computed<number | null>(() => {
  const v = points.value.find((p) => p.reference_max)?.reference_max
  return v ? Number(v.replace(',', '.')) : null
})

const chartData = computed(() => ({
  labels: points.value.map((p) => p.analysis_date),
  datasets: [
    {
      label: `${props.parameterName}, ${props.unit}`,
      data: points.value.map((p) => p.value_numeric),
      borderColor: '#1976d2',
      backgroundColor: 'rgba(25, 118, 210, 0.15)',
      tension: 0.25,
      spanGaps: true,
    },
  ],
}))

const annotations = computed(() => {
  if (refMin.value === null || refMax.value === null) return {}
  return {
    referenceZone: {
      type: 'box' as const,
      yMin: refMin.value,
      yMax: refMax.value,
      backgroundColor: 'rgba(76, 175, 80, 0.10)',
      borderColor: 'rgba(76, 175, 80, 0.4)',
      borderWidth: 1,
    },
  }
})

const chartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    annotation: { annotations: annotations.value },
    tooltip: {
      callbacks: {
        label: (ctx: { parsed: { y: number } }) => `${ctx.parsed.y} ${props.unit}`,
      },
    },
  },
  scales: { y: { beginAtZero: false } },
}))
</script>

<template>
  <div>
    <div class="d-flex align-center mb-2 gap-2">
      <span class="text-h6">{{ parameterName }}, {{ unit }}</span>
      <v-spacer />
      <v-btn-toggle v-model="range" mandatory density="compact" color="primary">
        <v-btn value="6m">6 мес</v-btn>
        <v-btn value="1y">1 год</v-btn>
        <v-btn value="5y">5 лет</v-btn>
        <v-btn value="all">Всё</v-btn>
      </v-btn-toggle>
    </div>
    <div v-if="points.length === 0 && !loading" class="text-disabled">
      Нет данных для построения графика.
    </div>
    <div v-else style="height: 280px">
      <Line :data="chartData" :options="chartOptions" />
    </div>
  </div>
</template>
