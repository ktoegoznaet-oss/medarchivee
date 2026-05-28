<script setup lang="ts">
import { ref, watch } from 'vue'
import { profileApi, type ICD10Entry } from '@/api/profile'

const props = defineProps<{ modelValue: ICD10Entry | null; label: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: ICD10Entry | null): void }>()

const query = ref('')
const items = ref<ICD10Entry[]>([])
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
      const { data } = await profileApi.searchIcd10(q)
      items.value = data
    } finally {
      loading.value = false
    }
  }, 250)
})

function onSelect(v: ICD10Entry | null) {
  emit('update:modelValue', v)
}
</script>

<template>
  <v-autocomplete
    :model-value="props.modelValue"
    :items="items"
    :item-title="(entry: ICD10Entry) => `${entry.code} — ${entry.name}`"
    :item-value="(entry: ICD10Entry) => entry"
    :label="props.label"
    :loading="loading"
    return-object
    no-filter
    clearable
    @update:search="(v: string) => (query = v)"
    @update:model-value="onSelect"
  />
</template>
