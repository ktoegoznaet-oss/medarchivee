import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  analysesApi,
  type AnalysesFilters,
  type AnalysisHistory,
  type AnalysisRecordCreate,
  type AnalysisRecordFull,
  type AnalysisRecordSummary,
} from '@/api/analyses'

export const useAnalysesStore = defineStore('analyses', () => {
  const records = ref<AnalysisRecordSummary[]>([])
  const currentRecord = ref<AnalysisRecordFull | null>(null)
  const loading = ref(false)

  async function fetchList(filters: AnalysesFilters = {}): Promise<void> {
    loading.value = true
    try {
      const { data } = await analysesApi.list(filters)
      records.value = data
    } finally {
      loading.value = false
    }
  }

  async function fetchRecord(id: number): Promise<AnalysisRecordFull> {
    const { data } = await analysesApi.get(id)
    currentRecord.value = data
    return data
  }

  async function createRecord(payload: AnalysisRecordCreate): Promise<AnalysisRecordFull> {
    const { data } = await analysesApi.create(payload)
    return data
  }

  async function deleteRecord(id: number): Promise<void> {
    await analysesApi.remove(id)
    records.value = records.value.filter((r) => r.id !== id)
  }

  async function fetchParameterHistory(
    code: string,
    dateFrom?: string,
    dateTo?: string,
  ): Promise<AnalysisHistory> {
    const { data } = await analysesApi.history(code, dateFrom, dateTo)
    return data
  }

  function reset(): void {
    records.value = []
    currentRecord.value = null
  }

  return {
    records,
    currentRecord,
    loading,
    fetchList,
    fetchRecord,
    createRecord,
    deleteRecord,
    fetchParameterHistory,
    reset,
  }
})
