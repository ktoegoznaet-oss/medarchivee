<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAnalysesStore } from '@/stores/analyses'
import { useProfileStore } from '@/stores/profile'
import { analysesApi, type AnalysisParameterSummary } from '@/api/analyses'
import ParameterAutocomplete from '@/components/analyses/ParameterAutocomplete.vue'

const { t } = useI18n()
const router = useRouter()
const store = useAnalysesStore()
const profileStore = useProfileStore()

interface ValueDraft {
  parameter: AnalysisParameterSummary | null
  parameter_name: string
  value: string
  unit: string
  reference_min: string
  reference_max: string
}

function emptyValue(): ValueDraft {
  return {
    parameter: null,
    parameter_name: '',
    value: '',
    unit: '',
    reference_min: '',
    reference_max: '',
  }
}

const form = reactive({
  analysis_date: new Date().toISOString().slice(0, 10),
  lab_name: '',
  doctor_referral: '',
  notes: '',
})

const values = ref<ValueDraft[]>([emptyValue()])
const submitting = ref(false)
const apiError = ref<string | null>(null)

function addValue(): void {
  values.value.push(emptyValue())
}

function removeValue(idx: number): void {
  if (values.value.length === 1) {
    values.value = [emptyValue()]
    return
  }
  values.value.splice(idx, 1)
}

async function onParameterSelected(draft: ValueDraft): Promise<void> {
  if (!draft.parameter) {
    return
  }
  draft.parameter_name = draft.parameter.name_ru
  draft.unit = draft.parameter.unit
  // Если у пользователя есть профиль — подтягиваем норму, иначе оставляем пустыми.
  if (profileStore.profile) {
    try {
      const gender = profileStore.profile.gender
      const age = computeAge(profileStore.profile.birth_date)
      const { data } = await analysesApi.parameterDetail(draft.parameter.code, gender, age)
      if (data.applicable_norm) {
        draft.reference_min =
          data.applicable_norm.min !== null ? String(data.applicable_norm.min) : ''
        draft.reference_max =
          data.applicable_norm.max !== null ? String(data.applicable_norm.max) : ''
      }
    } catch {
      /* graceful — оставляем пустыми, пользователь введёт сам */
    }
  }
}

function computeAge(birth: string): number {
  const today = new Date()
  const b = new Date(birth)
  let age = today.getFullYear() - b.getFullYear()
  if (
    today.getMonth() < b.getMonth() ||
    (today.getMonth() === b.getMonth() && today.getDate() < b.getDate())
  ) {
    age -= 1
  }
  return Math.max(age, 0)
}

const canSubmit = computed(
  () =>
    !submitting.value &&
    /^\d{4}-\d{2}-\d{2}$/.test(form.analysis_date) &&
    values.value.length > 0 &&
    values.value.every(
      (v) => v.parameter_name.trim().length > 0 && v.value.trim().length > 0 && v.unit.trim().length > 0,
    ),
)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  apiError.value = null
  try {
    await store.createRecord({
      analysis_date: form.analysis_date,
      lab_name: form.lab_name.trim() || null,
      doctor_referral: form.doctor_referral.trim() || null,
      notes: form.notes.trim() || null,
      values: values.value.map((v) => ({
        parameter_code: v.parameter?.code ?? null,
        parameter_name: v.parameter_name.trim(),
        value: v.value.trim(),
        unit: v.unit.trim(),
        reference_min: v.reference_min.trim() || null,
        reference_max: v.reference_max.trim() || null,
      })),
    })
    router.push({ name: 'analyses' })
  } catch (err: unknown) {
    apiError.value =
      (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
      t('analyses.errors.generic')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <v-container fluid>
    <h1 class="text-h4 mb-4">{{ t('analyses.create.title') }}</h1>
    <v-card class="pa-4 mb-4">
      <v-row dense>
        <v-col cols="12" md="4">
          <v-text-field
            v-model="form.analysis_date"
            :label="t('analyses.create.date')"
            type="date"
            required
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field v-model="form.lab_name" :label="t('analyses.create.lab')" />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field v-model="form.doctor_referral" :label="t('analyses.create.doctor')" />
        </v-col>
        <v-col cols="12">
          <v-textarea v-model="form.notes" :label="t('analyses.create.notes')" rows="2" auto-grow />
        </v-col>
      </v-row>
    </v-card>

    <v-card class="pa-4 mb-4">
      <div class="d-flex align-center mb-2">
        <span class="text-h6">{{ t('analyses.create.values_title') }}</span>
        <v-spacer />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="addValue">
          {{ t('analyses.create.add_value') }}
        </v-btn>
      </div>

      <div v-for="(draft, idx) in values" :key="idx" class="mb-4 pa-3" style="border: 1px solid #e0e0e0; border-radius: 4px;">
        <v-row dense>
          <v-col cols="12" md="6">
            <ParameterAutocomplete
              :model-value="draft.parameter"
              :label="t('analyses.create.parameter')"
              @update:model-value="(v) => { draft.parameter = v; onParameterSelected(draft) }"
            />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field
              v-model="draft.parameter_name"
              :label="t('analyses.create.parameter_name')"
              :hint="t('analyses.create.parameter_name_hint')"
              persistent-hint
              required
            />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="draft.value" :label="t('analyses.create.value')" required />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="draft.unit" :label="t('analyses.create.unit')" required />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="draft.reference_min" :label="t('analyses.create.ref_min')" />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model="draft.reference_max" :label="t('analyses.create.ref_max')" />
          </v-col>
        </v-row>
        <div class="d-flex justify-end">
          <v-btn variant="text" color="error" size="small" @click="removeValue(idx)">
            <v-icon icon="mdi-delete" start />
            {{ t('analyses.create.remove_value') }}
          </v-btn>
        </div>
      </div>
    </v-card>

    <v-alert v-if="apiError" type="error" class="mb-4">{{ apiError }}</v-alert>

    <div class="d-flex justify-end gap-2">
      <v-btn variant="text" @click="router.back()">{{ t('common.cancel') }}</v-btn>
      <v-btn color="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
        {{ t('common.save') }}
      </v-btn>
    </div>
  </v-container>
</template>
