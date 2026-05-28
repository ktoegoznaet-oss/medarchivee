<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { recoveryApi, type RecoveryLanguage } from '@/api/recovery'

const { t } = useI18n()
const router = useRouter()

type Phase = 'loading' | 'choose-lang' | 'show-phrase' | 'confirm' | 'done'

const phase = ref<Phase>('loading')
const lang = ref<RecoveryLanguage>('russian')
const phrase = ref<string>('')
const words = computed<string[]>(() => phrase.value.split(/\s+/).filter(Boolean))
const confirmationIndices = ref<number[]>([])
const confirmationInput = ref<string[]>(['', '', ''])
const acknowledged = ref(false)
const error = ref<string | null>(null)
const submitting = ref(false)

onMounted(async () => {
  try {
    const resp = await recoveryApi.status()
    if (resp.data.recovery_phrase_set) {
      // У пользователя уже есть recovery-фраза — отправляем на главную.
      router.push({ name: 'home' })
      return
    }
  } catch {
    // Если status упал — даём всё равно настроить фразу.
  }
  phase.value = 'choose-lang'
})

async function generate(): Promise<void> {
  error.value = null
  submitting.value = true
  try {
    const resp = await recoveryApi.generate(lang.value)
    phrase.value = resp.data.phrase
    confirmationIndices.value = resp.data.confirmation_indices
    confirmationInput.value = ['', '', '']
    phase.value = 'show-phrase'
  } catch {
    error.value = t('recovery.errors.generic')
  } finally {
    submitting.value = false
  }
}

async function copyPhrase(): Promise<void> {
  try {
    await navigator.clipboard.writeText(phrase.value)
  } catch {
    // ignore — Vuetify иначе сделает alert
  }
}

function downloadPhrase(): void {
  const blob = new Blob([phrase.value + '\n'], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'medarchive-recovery-phrase.txt'
  link.click()
  URL.revokeObjectURL(url)
}

async function submitConfirmation(): Promise<void> {
  error.value = null
  submitting.value = true
  try {
    await recoveryApi.confirm({
      phrase: phrase.value,
      lang: lang.value,
      confirmation_indices: confirmationIndices.value,
      confirmation_words: confirmationInput.value.map((w) => w.trim()),
    })
    phase.value = 'done'
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    const detail = e?.response?.data?.detail
    if (detail === 'phrase_confirmation_failed') {
      error.value = t('recovery.errors.confirmation_failed')
    } else if (detail === 'phrase_invalid') {
      error.value = t('recovery.errors.phrase_invalid')
    } else if (detail === 'phrase_already_set') {
      // Гонка — но уже OK.
      phase.value = 'done'
    } else {
      error.value = t('recovery.errors.generic')
    }
  } finally {
    submitting.value = false
  }
}

const canConfirm = computed(
  () =>
    acknowledged.value &&
    confirmationInput.value.every((w) => w.trim().length > 0) &&
    !submitting.value,
)
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="10" lg="8">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h5">{{ t('recovery.setup.title') }}</v-card-title>
          <v-card-text>
            <!-- Step 1: choose language -->
            <div v-if="phase === 'choose-lang'">
              <p class="mb-4">{{ t('recovery.setup.intro') }}</p>
              <v-radio-group v-model="lang">
                <v-radio :label="t('recovery.setup.lang_russian')" value="russian" />
                <v-radio :label="t('recovery.setup.lang_english')" value="english" />
              </v-radio-group>
              <v-btn color="primary" :loading="submitting" @click="generate">
                {{ t('recovery.setup.generate_phrase') }}
              </v-btn>
            </div>

            <!-- Step 2: show 12 words -->
            <div v-else-if="phase === 'show-phrase'">
              <v-alert type="warning" class="mb-4">
                {{ t('recovery.setup.warning') }}
              </v-alert>
              <v-row dense class="mb-4">
                <v-col
                  v-for="(word, idx) in words"
                  :key="idx"
                  cols="6"
                  sm="4"
                  md="3"
                >
                  <v-chip variant="outlined" class="mb-2" block>
                    <span class="font-weight-bold mr-2">{{ idx + 1 }}.</span>
                    {{ word }}
                  </v-chip>
                </v-col>
              </v-row>
              <div class="d-flex gap-2 mb-4">
                <v-btn variant="outlined" @click="copyPhrase">
                  {{ t('recovery.setup.copy') }}
                </v-btn>
                <v-btn variant="outlined" class="ml-2" @click="downloadPhrase">
                  {{ t('recovery.setup.download') }}
                </v-btn>
              </div>
              <v-btn color="primary" @click="phase = 'confirm'">
                {{ t('recovery.setup.saved_continue') }}
              </v-btn>
            </div>

            <!-- Step 3: confirm 3 random words -->
            <div v-else-if="phase === 'confirm'">
              <p class="mb-4">{{ t('recovery.setup.confirm_intro') }}</p>
              <div
                v-for="(wordPosition, slotIndex) in confirmationIndices"
                :key="wordPosition"
                class="mb-3"
              >
                <v-text-field
                  v-model="confirmationInput[slotIndex]"
                  :label="t('recovery.setup.word_at_position', { n: wordPosition + 1 })"
                  autocomplete="off"
                  density="compact"
                />
              </div>
              <v-checkbox
                v-model="acknowledged"
                :label="t('recovery.setup.acknowledge')"
                density="compact"
              />
              <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
              <v-btn
                color="primary"
                :loading="submitting"
                :disabled="!canConfirm"
                @click="submitConfirmation"
              >
                {{ t('recovery.setup.confirm') }}
              </v-btn>
              <v-btn
                variant="text"
                class="ml-2"
                :disabled="submitting"
                @click="phase = 'show-phrase'"
              >
                {{ t('recovery.setup.back') }}
              </v-btn>
            </div>

            <!-- Step 4: done -->
            <div v-else-if="phase === 'done'">
              <v-alert type="success" class="mb-4">
                {{ t('recovery.setup.success') }}
              </v-alert>
              <v-btn color="primary" @click="router.push({ name: 'home' })">
                {{ t('recovery.setup.go_home') }}
              </v-btn>
            </div>

            <!-- Loading -->
            <v-progress-circular
              v-else
              indeterminate
              color="primary"
            />
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
