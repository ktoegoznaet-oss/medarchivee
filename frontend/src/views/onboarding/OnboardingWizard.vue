<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useProfileStore } from '@/stores/profile'
import IcdAutocomplete from '@/components/IcdAutocomplete.vue'
import type { ICD10Entry } from '@/api/profile'
import type { AllergySeverity, Gender } from '@/api/profile'

const { t } = useI18n()
const router = useRouter()
const profileStore = useProfileStore()

const step = ref(1)
const submitting = ref(false)
const apiError = ref<string | null>(null)

const guessedTimezone =
  Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'Europe/Moscow'

const form = reactive({
  first_name: '',
  last_name: '',
  middle_name: '',
  birth_date: '',
  gender: 'not_specified' as Gender,
  height_cm: null as number | null,
  weight_kg: null as number | null,
  blood_type: null as string | null,
  city: '',
  timezone: guessedTimezone,
})

const bloodTypes = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
const today = new Date().toISOString().slice(0, 10)

const step1Valid = computed(
  () =>
    form.first_name.trim().length > 0 &&
    form.last_name.trim().length > 0 &&
    /^\d{4}-\d{2}-\d{2}$/.test(form.birth_date) &&
    form.birth_date <= today &&
    form.birth_date >= '1900-01-01' &&
    (['male', 'female', 'not_specified'] as Gender[]).includes(form.gender),
)

const step2Valid = computed(
  () =>
    (form.height_cm === null || (form.height_cm >= 30 && form.height_cm <= 250)) &&
    (form.weight_kg === null || (form.weight_kg >= 1 && form.weight_kg <= 500)),
)

interface ChronicDraft {
  name: string
  icd10_code: string | null
  diagnosed_at: string | null
}
interface AllergyDraft {
  allergen: string
  severity: AllergySeverity
}

const chronicDrafts = ref<ChronicDraft[]>([])
const allergyDrafts = ref<AllergyDraft[]>([])

const newChronic = reactive<{ icd: ICD10Entry | null; diagnosed_at: string }>({
  icd: null,
  diagnosed_at: '',
})
const newAllergy = reactive<{ allergen: string; severity: AllergySeverity }>({
  allergen: '',
  severity: 'mild',
})

function addChronicDraft(): void {
  if (!newChronic.icd) return
  chronicDrafts.value.push({
    name: newChronic.icd.name,
    icd10_code: newChronic.icd.code,
    diagnosed_at: newChronic.diagnosed_at || null,
  })
  newChronic.icd = null
  newChronic.diagnosed_at = ''
}

function removeChronicDraft(idx: number): void {
  chronicDrafts.value.splice(idx, 1)
}

function addAllergyDraft(): void {
  if (!newAllergy.allergen.trim()) return
  allergyDrafts.value.push({
    allergen: newAllergy.allergen.trim(),
    severity: newAllergy.severity,
  })
  newAllergy.allergen = ''
  newAllergy.severity = 'mild'
}

function removeAllergyDraft(idx: number): void {
  allergyDrafts.value.splice(idx, 1)
}

async function finish(): Promise<void> {
  submitting.value = true
  apiError.value = null
  try {
    await profileStore.createProfile({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      middle_name: form.middle_name.trim() || null,
      birth_date: form.birth_date,
      gender: form.gender,
      height_cm: form.height_cm,
      weight_kg: form.weight_kg,
      blood_type: form.blood_type,
      city: form.city.trim() || null,
      timezone: form.timezone,
    })
    for (const c of chronicDrafts.value) {
      await profileStore.addChronic({
        name: c.name,
        icd10_code: c.icd10_code,
        diagnosed_at: c.diagnosed_at,
        is_active: true,
      })
    }
    for (const a of allergyDrafts.value) {
      await profileStore.addAllergy({ allergen: a.allergen, severity: a.severity })
    }
    router.push({ name: 'home' })
  } catch (err: unknown) {
    apiError.value =
      (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
      t('onboarding.errors.generic')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="10" lg="8">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h5">{{ t('onboarding.title') }}</v-card-title>
          <v-stepper v-model="step" :items="[
            t('onboarding.step1.title'),
            t('onboarding.step2.title'),
            t('onboarding.step3.title'),
          ]">
            <template #item.1>
              <v-text-field
                v-model="form.first_name"
                :label="t('onboarding.step1.first_name')"
                required
              />
              <v-text-field
                v-model="form.last_name"
                :label="t('onboarding.step1.last_name')"
                required
              />
              <v-text-field
                v-model="form.middle_name"
                :label="t('onboarding.step1.middle_name')"
              />
              <v-text-field
                v-model="form.birth_date"
                :label="t('onboarding.step1.birth_date')"
                type="date"
                :max="today"
                min="1900-01-01"
                required
              />
              <v-radio-group v-model="form.gender" inline>
                <v-radio :label="t('onboarding.step1.gender_male')" value="male" />
                <v-radio :label="t('onboarding.step1.gender_female')" value="female" />
                <v-radio :label="t('onboarding.step1.gender_not_specified')" value="not_specified" />
              </v-radio-group>
            </template>

            <template #item.2>
              <v-text-field
                v-model.number="form.height_cm"
                :label="t('onboarding.step2.height_cm')"
                type="number"
                min="30"
                max="250"
              />
              <v-text-field
                v-model.number="form.weight_kg"
                :label="t('onboarding.step2.weight_kg')"
                type="number"
                min="1"
                max="500"
                step="0.1"
              />
              <v-select
                v-model="form.blood_type"
                :label="t('onboarding.step2.blood_type')"
                :items="bloodTypes"
                clearable
              />
              <v-text-field
                v-model="form.city"
                :label="t('onboarding.step2.city')"
              />
              <v-text-field
                v-model="form.timezone"
                :label="t('onboarding.step2.timezone')"
                :hint="t('onboarding.step2.timezone_hint')"
                persistent-hint
              />
            </template>

            <template #item.3>
              <h3 class="text-h6 mt-2">{{ t('onboarding.step3.chronic_title') }}</h3>
              <div class="d-flex align-center gap-2 mt-2">
                <IcdAutocomplete
                  v-model="newChronic.icd"
                  :label="t('onboarding.step3.chronic_name')"
                />
                <v-text-field
                  v-model="newChronic.diagnosed_at"
                  :label="t('onboarding.step3.chronic_date')"
                  type="date"
                />
                <v-btn color="primary" variant="tonal" @click="addChronicDraft">
                  {{ t('onboarding.step3.add') }}
                </v-btn>
              </div>
              <v-list density="compact">
                <v-list-item
                  v-for="(c, idx) in chronicDrafts"
                  :key="idx"
                  :title="`${c.icd10_code ?? ''} ${c.name}`"
                  :subtitle="c.diagnosed_at ?? ''"
                >
                  <template #append>
                    <v-btn icon="mdi-close" size="x-small" variant="text" @click="removeChronicDraft(idx)" />
                  </template>
                </v-list-item>
              </v-list>

              <v-divider class="my-4" />

              <h3 class="text-h6">{{ t('onboarding.step3.allergy_title') }}</h3>
              <div class="d-flex align-center gap-2 mt-2">
                <v-text-field
                  v-model="newAllergy.allergen"
                  :label="t('onboarding.step3.allergen')"
                />
                <v-select
                  v-model="newAllergy.severity"
                  :label="t('onboarding.step3.severity')"
                  :items="[
                    { title: t('severity.mild'), value: 'mild' },
                    { title: t('severity.moderate'), value: 'moderate' },
                    { title: t('severity.severe'), value: 'severe' },
                    { title: t('severity.life_threatening'), value: 'life_threatening' },
                  ]"
                />
                <v-btn color="primary" variant="tonal" @click="addAllergyDraft">
                  {{ t('onboarding.step3.add') }}
                </v-btn>
              </div>
              <v-list density="compact">
                <v-list-item
                  v-for="(a, idx) in allergyDrafts"
                  :key="idx"
                  :title="a.allergen"
                  :subtitle="t(`severity.${a.severity}`)"
                >
                  <template #append>
                    <v-btn icon="mdi-close" size="x-small" variant="text" @click="removeAllergyDraft(idx)" />
                  </template>
                </v-list-item>
              </v-list>
            </template>

            <template #actions>
              <v-card-actions>
                <v-btn
                  v-if="step > 1"
                  variant="text"
                  @click="step = step - 1"
                >
                  {{ t('onboarding.back') }}
                </v-btn>
                <v-spacer />
                <v-btn
                  v-if="step < 3"
                  color="primary"
                  :disabled="(step === 1 && !step1Valid) || (step === 2 && !step2Valid)"
                  @click="step = step + 1"
                >
                  {{ t('onboarding.next') }}
                </v-btn>
                <v-btn
                  v-else
                  color="primary"
                  :loading="submitting"
                  @click="finish"
                >
                  {{ t('onboarding.finish') }}
                </v-btn>
              </v-card-actions>
            </template>
          </v-stepper>
          <v-alert v-if="apiError" type="error" class="mt-4">{{ apiError }}</v-alert>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
