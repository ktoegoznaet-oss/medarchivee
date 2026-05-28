<script setup lang="ts">
import { computed } from 'vue'
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
import type { WeightRecord } from '@/api/profile'

ChartJS.register(CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Legend)

const props = defineProps<{ records: WeightRecord[] }>()

const chartData = computed(() => {
  const ordered = [...props.records].sort((a, b) =>
    a.recorded_at < b.recorded_at ? -1 : 1,
  )
  return {
    labels: ordered.map((r) => r.recorded_at.slice(0, 10)),
    datasets: [
      {
        label: 'кг',
        data: ordered.map((r) => r.weight_kg),
        borderColor: '#1976d2',
        backgroundColor: 'rgba(25, 118, 210, 0.15)',
        tension: 0.25,
        fill: true,
      },
    ],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: { y: { beginAtZero: false } },
}
</script>

<template>
  <div style="height: 240px">
    <Line :data="chartData" :options="chartOptions" />
  </div>
</template>
