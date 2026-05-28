<script setup lang="ts">
import { ref, watch } from 'vue'
import { analysesApi, type AnalysisParameterSummary } from '@/api/analyses'

const props = defineProps<{ modelValue: AnalysisParameterSummary | null; label: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: AnalysisParameterSummary | null): void }>()

const query = ref('')
const items = ref<AnalysisParameterSummary[]>([])
const loading = ref(false)

let debounce: ReturnType<typeof setTimeout> | null = null

watch(query, (q) => {
  if (debounce) clearTimeout(debounce)
  if (!q || q.length < 2) {
    items.value = []
    return
  }
  debounce = setTimeout(async () => {
    loading.value = true
    try {
      const { data } = await analysesApi.searchParameters(q)
      items.value = data
    } finally {
      loading.value = false
    }
  }, 250)
})

function onSelect(v: AnalysisParameterSummary | null) {
  emit('update:modelValue', v)
}
</script>

<template>
  <v-autocomplete
    :model-value="props.modelValue"
    :items="items"
    :item-title="(p: AnalysisParameterSummary) => `${p.name_ru} (${p.unit}) — ${p.category}`"
    :item-value="(p: AnalysisParameterSummary) => p"
    :label="props.label"
    :loading="loading"
    return-object
    no-filter
    clearable
    @update:search="(v: string) => (query = v)"
    @update:model-value="onSelect"
  />
</template>
