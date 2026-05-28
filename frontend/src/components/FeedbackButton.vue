<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { ticketsApi, type TicketType } from '@/api/tickets'

const { t } = useI18n()
const route = useRoute()

const open = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)
const submitted = ref(false)

const form = ref<{
  type: TicketType
  title: string
  description: string
  screenshot: File | null
}>({
  type: 'bug',
  title: '',
  description: '',
  screenshot: null,
})

const screenshotInput = ref<HTMLInputElement | null>(null)

const canSubmit = computed(
  () =>
    !submitting.value &&
    form.value.title.trim().length > 0 &&
    form.value.title.length <= 120 &&
    form.value.description.trim().length > 0 &&
    form.value.description.length <= 5000,
)

watch(open, (val) => {
  if (val) {
    submitted.value = false
    error.value = null
    form.value = { type: 'bug', title: '', description: '', screenshot: null }
  }
})

function onScreenshotChange(event: Event): void {
  const files = (event.target as HTMLInputElement).files
  form.value.screenshot = files && files.length > 0 ? files[0] : null
}

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = null
  try {
    await ticketsApi.create(
      {
        type: form.value.type,
        title: form.value.title.trim(),
        description: form.value.description.trim(),
        url: window.location.href,
        user_agent: navigator.userAgent,
        screen_size: `${window.screen.width}x${window.screen.height}`,
      },
      form.value.screenshot,
    )
    submitted.value = true
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string }; status?: number } }
    const detail = e?.response?.data?.detail
    if (detail === 'attachment_too_large') {
      error.value = t('feedback.errors.attachment_too_large')
    } else if (detail === 'attachment_type_not_allowed') {
      error.value = t('feedback.errors.attachment_type_not_allowed')
    } else {
      error.value = t('feedback.errors.generic')
    }
  } finally {
    submitting.value = false
  }
}

const hideOnRoute = computed(() => {
  // Скрываем кнопку на гостевых страницах (login/register/etc).
  const name = route.name?.toString() ?? ''
  return ['login', 'register', 'verify-email', 'forgot-password', 'recovery-phrase'].includes(name)
})
</script>

<template>
  <div v-if="!hideOnRoute">
    <v-btn
      icon
      color="primary"
      size="large"
      style="position: fixed; bottom: 24px; right: 24px; z-index: 100;"
      @click="open = true"
    >
      <v-icon>mdi-message-alert</v-icon>
      <v-tooltip activator="parent" location="left">
        {{ t('feedback.button') }}
      </v-tooltip>
    </v-btn>

    <v-dialog v-model="open" max-width="600">
      <v-card>
        <v-card-title>{{ t('feedback.dialog_title') }}</v-card-title>
        <v-card-text>
          <div v-if="submitted">
            <v-alert type="success" class="mb-4">
              {{ t('feedback.submitted') }}
            </v-alert>
            <p>{{ t('feedback.submitted_more') }}</p>
          </div>

          <v-form v-else @submit.prevent="submit">
            <p class="text-caption mb-3 text-warning">
              {{ t('feedback.warning_no_medical') }}
            </p>

            <v-select
              v-model="form.type"
              :label="t('feedback.type_label')"
              :items="[
                { title: t('feedback.types.bug'), value: 'bug' },
                { title: t('feedback.types.suggestion'), value: 'suggestion' },
                { title: t('feedback.types.question'), value: 'question' },
                { title: t('feedback.types.other'), value: 'other' },
              ]"
              density="compact"
            />
            <v-text-field
              v-model="form.title"
              :label="t('feedback.title_label')"
              :counter="120"
              :maxlength="120"
              density="compact"
              required
            />
            <v-textarea
              v-model="form.description"
              :label="t('feedback.description_label')"
              :counter="5000"
              :maxlength="5000"
              rows="5"
              auto-grow
              required
            />
            <div class="mb-3">
              <label class="text-caption d-block mb-1">
                {{ t('feedback.screenshot_label') }}
              </label>
              <input
                ref="screenshotInput"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                @change="onScreenshotChange"
              />
              <div class="text-caption mt-1 text-disabled">
                {{ t('feedback.screenshot_hint') }}
              </div>
            </div>

            <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn v-if="!submitted" :disabled="submitting" @click="open = false">
            {{ t('common.cancel') }}
          </v-btn>
          <v-btn
            v-if="!submitted"
            color="primary"
            :loading="submitting"
            :disabled="!canSubmit"
            @click="submit"
          >
            {{ t('feedback.submit') }}
          </v-btn>
          <v-btn v-else color="primary" @click="open = false">
            {{ t('common.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
