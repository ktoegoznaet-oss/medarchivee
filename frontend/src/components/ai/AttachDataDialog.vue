<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAnalysesStore } from '@/stores/analyses'
import { useProfileStore } from '@/stores/profile'
import type { AttachedData } from '@/api/ai'

const props = defineProps<{
  modelValue: boolean
  initial?: AttachedData | null
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'attached', data: AttachedData | null): void
}>()

const { t } = useI18n()
const profileStore = useProfileStore()
const analysesStore = useAnalysesStore()

const tab = ref<'profile' | 'analyses'>('profile')
const includeProfile = ref(false)
const selectedAnalyses = ref<number[]>([])

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    includeProfile.value = props.initial?.include_profile ?? false
    // Копируем массив, чтобы мутации внутри диалога (push/filter) не
    // протекали в родительский state до подтверждения «Прикрепить».
    selectedAnalyses.value = [...(props.initial?.analysis_ids ?? [])]
    if (!profileStore.profileChecked) await profileStore.fetchProfile()
    if (analysesStore.records.length === 0) await analysesStore.fetchList()
  },
)

const previewText = computed(() => {
  const parts: string[] = []
  if (includeProfile.value) parts.push(t('ai.attach.preview_profile'))
  if (selectedAnalyses.value.length > 0) {
    parts.push(
      t(
        'ai.attach.preview_analyses',
        { count: selectedAnalyses.value.length },
        selectedAnalyses.value.length,
      ),
    )
  }
  return parts.length === 0 ? t('ai.attach.preview_empty') : parts.join(' + ')
})

function toggleAnalysis(id: number, value: boolean | null): void {
  if (value) {
    if (!selectedAnalyses.value.includes(id)) selectedAnalyses.value.push(id)
  } else {
    selectedAnalyses.value = selectedAnalyses.value.filter((x) => x !== id)
  }
}

function close(): void {
  emit('update:modelValue', false)
}

function confirm(): void {
  if (!includeProfile.value && selectedAnalyses.value.length === 0) {
    emit('attached', null)
  } else {
    emit('attached', {
      include_profile: includeProfile.value,
      analysis_ids: [...selectedAnalyses.value],
    })
  }
  close()
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="640"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title>{{ t('ai.attach.title') }}</v-card-title>
      <v-card-subtitle>{{ t('ai.attach.subtitle') }}</v-card-subtitle>

      <v-tabs v-model="tab" color="primary">
        <v-tab value="profile">{{ t('ai.attach.tab_profile') }}</v-tab>
        <v-tab value="analyses">{{ t('ai.attach.tab_analyses') }}</v-tab>
      </v-tabs>

      <v-card-text>
        <v-window v-model="tab">
          <v-window-item value="profile">
            <p v-if="!profileStore.profile" class="text-disabled">
              {{ t('ai.attach.no_profile') }}
            </p>
            <v-checkbox
              v-else
              v-model="includeProfile"
              :label="t('ai.attach.include_profile')"
            />
          </v-window-item>

          <v-window-item value="analyses">
            <p v-if="analysesStore.records.length === 0" class="text-disabled">
              {{ t('ai.attach.no_analyses') }}
            </p>
            <v-list v-else density="compact" select-strategy="multiple">
              <v-list-item
                v-for="r in analysesStore.records"
                :key="r.id"
                :title="r.analysis_date"
                :subtitle="r.lab_name ?? t('analyses.list.no_lab')"
              >
                <template #prepend>
                  <v-checkbox
                    :model-value="selectedAnalyses.includes(r.id)"
                    hide-details
                    @update:model-value="(v) => toggleAnalysis(r.id, v)"
                  />
                </template>
              </v-list-item>
            </v-list>
          </v-window-item>
        </v-window>

        <v-divider class="my-3" />
        <p class="text-subtitle-2">{{ t('ai.attach.preview_label') }}</p>
        <p>{{ previewText }}</p>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close">{{ t('common.cancel') }}</v-btn>
        <v-btn color="primary" variant="elevated" @click="confirm">
          {{ t('ai.attach.attach') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
