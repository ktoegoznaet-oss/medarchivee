<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProfileStore } from '@/stores/profile'
import WeightChart from '@/components/WeightChart.vue'
import type { AllergyPayload, ChronicConditionPayload } from '@/api/profile'

const { t } = useI18n()
const profileStore = useProfileStore()

const editDialog = ref(false)
const editDraft = ref<Record<string, unknown>>({})

const weightDialog = ref(false)
const newWeight = ref<number | null>(null)
const newWeightNote = ref('')

const chronicDialog = ref(false)
const newChronic = ref<ChronicConditionPayload>({ name: '', is_active: true })

const allergyDialog = ref(false)
const newAllergy = ref<AllergyPayload>({ allergen: '', severity: 'mild' })

onMounted(async () => {
  await Promise.all([
    profileStore.fetchProfile(),
    profileStore.fetchWeightHistory(),
    profileStore.fetchChronic(),
    profileStore.fetchAllergies(),
  ])
})

const severityColor: Record<string, string> = {
  mild: 'green',
  moderate: 'orange',
  severe: 'red',
  life_threatening: 'red-darken-3',
}

const showWeightChart = computed(() => profileStore.weightHistory.length >= 2)

function openEdit(): void {
  editDraft.value = { ...(profileStore.profile ?? {}) }
  editDialog.value = true
}

async function saveEdit(): Promise<void> {
  await profileStore.updateProfile(editDraft.value)
  editDialog.value = false
}

async function saveWeight(): Promise<void> {
  if (newWeight.value === null) return
  await profileStore.addWeightRecord(newWeight.value, newWeightNote.value || undefined)
  newWeight.value = null
  newWeightNote.value = ''
  weightDialog.value = false
}

async function saveChronic(): Promise<void> {
  if (!newChronic.value.name) return
  await profileStore.addChronic(newChronic.value)
  newChronic.value = { name: '', is_active: true }
  chronicDialog.value = false
}

async function toggleChronic(id: number, isActive: boolean): Promise<void> {
  await profileStore.updateChronic(id, { is_active: !isActive })
}

async function removeChronic(id: number): Promise<void> {
  await profileStore.deleteChronic(id)
}

async function saveAllergy(): Promise<void> {
  if (!newAllergy.value.allergen) return
  await profileStore.addAllergy(newAllergy.value)
  newAllergy.value = { allergen: '', severity: 'mild' }
  allergyDialog.value = false
}

async function removeAllergy(id: number): Promise<void> {
  await profileStore.deleteAllergy(id)
}
</script>

<template>
  <v-container fluid>
    <v-row>
      <v-col cols="12" md="6">
        <v-card class="pa-4 mb-4">
          <v-card-title class="d-flex align-center">
            <span>{{ t('profile.basic_title') }}</span>
            <v-spacer />
            <v-btn variant="text" size="small" @click="openEdit">
              <v-icon icon="mdi-pencil" start />
              {{ t('profile.edit') }}
            </v-btn>
          </v-card-title>
          <v-card-text v-if="profileStore.profile">
            <p>
              <strong>{{ profileStore.profile.last_name }}
                {{ profileStore.profile.first_name }}
                {{ profileStore.profile.middle_name }}</strong>
            </p>
            <p>{{ t('profile.birth_date') }}: {{ profileStore.profile.birth_date }}</p>
            <p>{{ t('profile.gender') }}: {{ t(`gender.${profileStore.profile.gender}`) }}</p>
            <p v-if="profileStore.profile.city">
              {{ t('profile.city') }}: {{ profileStore.profile.city }}
            </p>
            <p v-if="profileStore.profile.timezone">
              {{ t('profile.timezone') }}: {{ profileStore.profile.timezone }}
            </p>
          </v-card-text>
        </v-card>

        <v-card class="pa-4 mb-4">
          <v-card-title class="d-flex align-center">
            <span>{{ t('profile.physical_title') }}</span>
            <v-spacer />
            <v-btn variant="text" size="small" @click="weightDialog = true">
              <v-icon icon="mdi-plus" start />
              {{ t('profile.add_weight') }}
            </v-btn>
          </v-card-title>
          <v-card-text v-if="profileStore.profile">
            <p v-if="profileStore.profile.height_cm">
              {{ t('profile.height') }}: {{ profileStore.profile.height_cm }} {{ t('profile.cm') }}
            </p>
            <p v-if="profileStore.profile.weight_kg">
              {{ t('profile.weight') }}: {{ profileStore.profile.weight_kg }} {{ t('profile.kg') }}
            </p>
            <p v-if="profileStore.profile.blood_type">
              {{ t('profile.blood_type') }}: {{ profileStore.profile.blood_type }}
            </p>
            <WeightChart v-if="showWeightChart" :records="profileStore.weightHistory" />
          </v-card-text>
        </v-card>

        <v-card class="pa-4 mb-4">
          <v-card-title>{{ t('profile.contacts_title') }}</v-card-title>
          <v-card-text v-if="profileStore.profile">
            <p>{{ t('profile.emergency_contact') }}: {{ profileStore.profile.emergency_contact || '—' }}</p>
            <p>{{ t('profile.insurance_info') }}: {{ profileStore.profile.insurance_info || '—' }}</p>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card class="pa-4 mb-4">
          <v-card-title class="d-flex align-center">
            <span>{{ t('profile.chronic_title') }}</span>
            <v-spacer />
            <v-btn variant="text" size="small" @click="chronicDialog = true">
              <v-icon icon="mdi-plus" start />
              {{ t('profile.add') }}
            </v-btn>
          </v-card-title>
          <v-list>
            <v-list-item v-for="c in profileStore.chronicConditions" :key="c.id">
              <template #title>
                <span :class="{ 'text-disabled': !c.is_active }">
                  {{ c.icd10_code ? `${c.icd10_code} — ` : '' }}{{ c.name }}
                </span>
              </template>
              <template #subtitle>
                <span v-if="c.diagnosed_at">{{ t('profile.diagnosed_at') }}: {{ c.diagnosed_at }}</span>
              </template>
              <template #append>
                <v-btn
                  variant="text"
                  size="x-small"
                  @click="toggleChronic(c.id, c.is_active)"
                >
                  {{ c.is_active ? t('profile.mark_inactive') : t('profile.mark_active') }}
                </v-btn>
                <v-btn
                  icon="mdi-delete"
                  variant="text"
                  size="x-small"
                  @click="removeChronic(c.id)"
                />
              </template>
            </v-list-item>
            <v-list-item v-if="profileStore.chronicConditions.length === 0">
              <v-list-item-title class="text-disabled">
                {{ t('profile.empty_list') }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>

        <v-card class="pa-4 mb-4">
          <v-card-title class="d-flex align-center">
            <span>{{ t('profile.allergies_title') }}</span>
            <v-spacer />
            <v-btn variant="text" size="small" @click="allergyDialog = true">
              <v-icon icon="mdi-plus" start />
              {{ t('profile.add') }}
            </v-btn>
          </v-card-title>
          <v-list>
            <v-list-item v-for="a in profileStore.allergies" :key="a.id">
              <template #title>
                <v-chip
                  :color="severityColor[a.severity]"
                  size="small"
                  class="mr-2"
                  variant="tonal"
                >
                  {{ t(`severity.${a.severity}`) }}
                </v-chip>
                {{ a.allergen }}
              </template>
              <template #append>
                <v-btn
                  icon="mdi-delete"
                  variant="text"
                  size="x-small"
                  @click="removeAllergy(a.id)"
                />
              </template>
            </v-list-item>
            <v-list-item v-if="profileStore.allergies.length === 0">
              <v-list-item-title class="text-disabled">
                {{ t('profile.empty_list') }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
    </v-row>

    <!-- Edit basic dialog -->
    <v-dialog v-model="editDialog" max-width="500">
      <v-card class="pa-4">
        <v-card-title>{{ t('profile.edit') }}</v-card-title>
        <v-card-text>
          <v-text-field
            :model-value="(editDraft.first_name as string) || ''"
            :label="t('onboarding.step1.first_name')"
            @update:model-value="(v: string) => (editDraft.first_name = v)"
          />
          <v-text-field
            :model-value="(editDraft.last_name as string) || ''"
            :label="t('onboarding.step1.last_name')"
            @update:model-value="(v: string) => (editDraft.last_name = v)"
          />
          <v-text-field
            :model-value="(editDraft.city as string) || ''"
            :label="t('profile.city')"
            @update:model-value="(v: string) => (editDraft.city = v)"
          />
          <v-text-field
            :model-value="(editDraft.emergency_contact as string) || ''"
            :label="t('profile.emergency_contact')"
            @update:model-value="(v: string) => (editDraft.emergency_contact = v)"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="editDialog = false">{{ t('common.cancel') }}</v-btn>
          <v-btn color="primary" @click="saveEdit">{{ t('common.save') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add weight dialog -->
    <v-dialog v-model="weightDialog" max-width="400">
      <v-card class="pa-4">
        <v-card-title>{{ t('profile.add_weight') }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model.number="newWeight"
            :label="t('profile.weight')"
            type="number"
            min="1"
            max="500"
            step="0.1"
          />
          <v-text-field
            v-model="newWeightNote"
            :label="t('profile.note')"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="weightDialog = false">{{ t('common.cancel') }}</v-btn>
          <v-btn color="primary" :disabled="newWeight === null" @click="saveWeight">
            {{ t('common.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add chronic dialog -->
    <v-dialog v-model="chronicDialog" max-width="500">
      <v-card class="pa-4">
        <v-card-title>{{ t('profile.add_chronic') }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="newChronic.name" :label="t('onboarding.step3.chronic_name')" />
          <v-text-field v-model="newChronic.icd10_code" label="ICD-10" />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="chronicDialog = false">{{ t('common.cancel') }}</v-btn>
          <v-btn color="primary" @click="saveChronic">{{ t('common.save') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add allergy dialog -->
    <v-dialog v-model="allergyDialog" max-width="500">
      <v-card class="pa-4">
        <v-card-title>{{ t('profile.add_allergy') }}</v-card-title>
        <v-card-text>
          <v-text-field v-model="newAllergy.allergen" :label="t('onboarding.step3.allergen')" />
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
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="allergyDialog = false">{{ t('common.cancel') }}</v-btn>
          <v-btn color="primary" @click="saveAllergy">{{ t('common.save') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
