<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTelegramStore } from '@/stores/telegram'

const { t } = useI18n()
const store = useTelegramStore()

const errorMessage = ref<string | null>(null)
const testStatus = ref<'idle' | 'sending' | 'sent' | 'failed'>('idle')
const unbindDialog = ref(false)
const codeCountdown = ref<number>(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const binding = computed(() => store.binding)
const code = computed(() => store.bindingCode)

const codeFormatted = computed(() => {
  const c = code.value?.code
  if (!c) return ''
  // 123 456 — пробел в середине для читаемости.
  return c.slice(0, 3) + ' ' + c.slice(3)
})

const countdownLabel = computed(() => {
  const sec = codeCountdown.value
  if (sec <= 0) return t('telegram.code_expired_label')
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return t('telegram.code_valid_for', {
    time: `${m}:${s.toString().padStart(2, '0')}`,
  })
})

const boundDate = computed(() => {
  if (!binding.value?.bound_at) return ''
  return new Date(binding.value.bound_at).toLocaleString('ru-RU')
})

function startCountdown(): void {
  stopCountdown()
  countdownTimer = setInterval(() => {
    if (!code.value) {
      codeCountdown.value = 0
      stopCountdown()
      return
    }
    const diff = Math.max(
      0,
      Math.floor(
        (new Date(code.value.expires_at).getTime() - Date.now()) / 1000,
      ),
    )
    codeCountdown.value = diff
    if (diff <= 0) {
      stopCountdown()
      store.clearCode()
    }
  }, 1000)
}

function stopCountdown(): void {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

async function generate(): Promise<void> {
  errorMessage.value = null
  try {
    const data = await store.generateCode()
    codeCountdown.value = Math.max(
      0,
      Math.floor((new Date(data.expires_at).getTime() - Date.now()) / 1000),
    )
    startCountdown()
  } catch (err) {
    const detail =
      (err as { response?: { status?: number; data?: { detail?: string } } })
        .response?.data?.detail ?? null
    errorMessage.value = detail ?? t('telegram.errors.generic')
  }
}

async function confirmUnbind(): Promise<void> {
  errorMessage.value = null
  try {
    await store.unbind()
    await store.fetchBinding()
  } catch {
    errorMessage.value = t('telegram.errors.generic')
  } finally {
    unbindDialog.value = false
  }
}

async function sendTest(): Promise<void> {
  testStatus.value = 'sending'
  try {
    const ok = await store.sendTestMessage()
    testStatus.value = ok ? 'sent' : 'failed'
  } catch {
    testStatus.value = 'failed'
  }
}

async function updateSwitch(field: string, value: boolean): Promise<void> {
  await store.updateSettings({ [field]: value } as Record<string, boolean>)
}

watch(code, (c) => {
  if (c) {
    codeCountdown.value = Math.max(
      0,
      Math.floor((new Date(c.expires_at).getTime() - Date.now()) / 1000),
    )
    startCountdown()
  }
})

const initialFetchFailed = ref(false)

async function loadBinding(): Promise<void> {
  initialFetchFailed.value = false
  try {
    await store.fetchBinding()
  } catch {
    // Bind с сервера не пришёл — даём пользователю кнопку «Повторить»,
    // чтобы не зависало «Загрузка…» навсегда (см. R8 в DIAGNOSTIC_REPORT.md).
    initialFetchFailed.value = true
  }
}

onMounted(loadBinding)

onUnmounted(() => {
  stopCountdown()
})
</script>

<template>
  <v-container fluid class="settings-telegram">
    <h1 class="text-h4 mb-4">{{ t('telegram.title') }}</h1>

    <v-alert type="warning" variant="tonal" class="mb-4" border="start">
      {{ t('telegram.disclaimer') }}
    </v-alert>

    <v-alert
      v-if="errorMessage"
      type="error"
      density="compact"
      class="mb-3"
      closable
      @click:close="errorMessage = null"
    >
      {{ errorMessage }}
    </v-alert>

    <!-- Состояние «не привязан» -->
    <v-card v-if="binding && !binding.bound" class="pa-4 mb-4">
      <p class="mb-3">{{ t('telegram.unbound_intro') }}</p>

      <div v-if="!code">
        <v-btn color="primary" prepend-icon="mdi-link" @click="generate">
          {{ t('telegram.generate_code') }}
        </v-btn>
      </div>

      <div v-else>
        <p class="text-h3 font-weight-bold font-mono text-center my-3">
          {{ codeFormatted }}
        </p>
        <p class="text-center text-disabled">{{ countdownLabel }}</p>
        <div class="d-flex justify-center gap-2 mt-3">
          <v-btn
            color="primary"
            :href="code.deep_link"
            target="_blank"
            prepend-icon="mdi-open-in-new"
          >
            {{ t('telegram.open_in_telegram') }}
          </v-btn>
          <v-btn variant="text" @click="generate">
            {{ t('telegram.regenerate') }}
          </v-btn>
        </div>
      </div>
    </v-card>

    <!-- Состояние «привязан» -->
    <v-card v-else-if="binding && binding.bound" class="pa-4 mb-4">
      <div class="d-flex align-center mb-2">
        <v-icon icon="mdi-telegram" color="primary" class="me-2" size="32" />
        <div>
          <p class="text-subtitle-1 mb-0">
            {{
              t('telegram.bound_as', {
                name: binding.telegram_username ? `@${binding.telegram_username}` : t('telegram.no_username'),
              })
            }}
          </p>
          <p class="text-caption text-disabled">
            {{ t('telegram.bound_at', { date: boundDate }) }}
          </p>
        </div>
      </div>

      <v-divider class="my-3" />

      <h3 class="text-subtitle-1 mb-2">{{ t('telegram.notifications') }}</h3>
      <v-switch
        :model-value="binding.notifications_enabled"
        :label="t('telegram.notify_all')"
        color="primary"
        hide-details
        @update:model-value="(v) => updateSwitch('notifications_enabled', !!v)"
      />
      <v-switch
        :model-value="binding.notify_medications"
        color="primary"
        hide-details
        @update:model-value="(v) => updateSwitch('notify_medications', !!v)"
      >
        <template #label>
          💊 {{ t('telegram.notify_medications') }}
          <span class="text-caption text-disabled ms-2">
            ({{ t('telegram.stage_10') }})
          </span>
        </template>
      </v-switch>
      <v-switch
        :model-value="binding.notify_visits"
        color="primary"
        hide-details
        @update:model-value="(v) => updateSwitch('notify_visits', !!v)"
      >
        <template #label>
          🏥 {{ t('telegram.notify_visits') }}
          <span class="text-caption text-disabled ms-2">
            ({{ t('telegram.stage_9') }})
          </span>
        </template>
      </v-switch>
      <v-switch
        :model-value="binding.notify_daily_summary"
        color="primary"
        hide-details
        @update:model-value="(v) => updateSwitch('notify_daily_summary', !!v)"
      >
        <template #label>
          📅 {{ t('telegram.notify_daily_summary') }}
          <span class="text-caption text-disabled ms-2">
            ({{ t('telegram.stage_10') }})
          </span>
        </template>
      </v-switch>

      <v-divider class="my-3" />

      <div class="d-flex flex-wrap gap-2">
        <v-btn
          variant="tonal"
          color="primary"
          prepend-icon="mdi-send"
          :loading="testStatus === 'sending'"
          @click="sendTest"
        >
          {{ t('telegram.send_test') }}
        </v-btn>
        <v-alert
          v-if="testStatus === 'sent'"
          type="success"
          density="compact"
          class="mb-0"
          closable
          @click:close="testStatus = 'idle'"
        >
          {{ t('telegram.test_sent') }}
        </v-alert>
        <v-alert
          v-if="testStatus === 'failed'"
          type="error"
          density="compact"
          class="mb-0"
          closable
          @click:close="testStatus = 'idle'"
        >
          {{ t('telegram.test_failed') }}
        </v-alert>
        <v-spacer />
        <v-btn
          variant="text"
          color="error"
          prepend-icon="mdi-link-off"
          @click="unbindDialog = true"
        >
          {{ t('telegram.unbind') }}
        </v-btn>
      </div>
    </v-card>

    <div v-else>
      <v-alert
        v-if="initialFetchFailed"
        type="error"
        density="compact"
        class="mb-2"
      >
        {{ t('telegram.fetch_failed') }}
        <template #append>
          <v-btn variant="text" size="small" @click="loadBinding">
            {{ t('telegram.retry') }}
          </v-btn>
        </template>
      </v-alert>
      <p v-else class="text-disabled">{{ t('telegram.loading') }}</p>
    </div>

    <v-dialog v-model="unbindDialog" max-width="420">
      <v-card class="pa-4">
        <v-card-title>{{ t('telegram.unbind_confirm_title') }}</v-card-title>
        <v-card-text>{{ t('telegram.unbind_confirm_text') }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="unbindDialog = false">
            {{ t('common.cancel') }}
          </v-btn>
          <v-btn color="error" @click="confirmUnbind">
            {{ t('telegram.unbind') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<style scoped>
.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  letter-spacing: 0.1em;
}
.gap-2 {
  gap: 0.5rem;
}
</style>
