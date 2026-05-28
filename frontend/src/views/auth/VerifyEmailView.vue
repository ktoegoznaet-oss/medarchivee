<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const userId = Number(route.query.user_id)
const code = ref('')
const submitting = ref(false)
const resending = ref(false)
const apiError = ref<string | null>(null)
const info = ref<string | null>(null)

const canSubmit = computed(
  () => !submitting.value && /^\d{6}$/.test(code.value) && Number.isFinite(userId),
)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  apiError.value = null
  try {
    await auth.verifyEmail({ user_id: userId, code: code.value })
    router.push({ name: 'login' })
  } catch (err: unknown) {
    apiError.value = mapError(err)
  } finally {
    submitting.value = false
  }
}

async function resend(): Promise<void> {
  resending.value = true
  apiError.value = null
  info.value = null
  try {
    await authApi.resendVerification(userId)
    info.value = t('auth.verify_email.resent')
  } catch (err: unknown) {
    apiError.value = mapError(err)
  } finally {
    resending.value = false
  }
}

function mapError(err: unknown): string {
  const e = err as { response?: { data?: { detail?: string }; status?: number } }
  const detail = e?.response?.data?.detail
  if (detail === 'verification_code_invalid') return t('auth.errors.verification_invalid')
  if (detail === 'verification_code_expired') return t('auth.errors.verification_expired')
  if (detail === 'resend_too_soon') return t('auth.errors.resend_too_soon')
  return t('auth.errors.generic')
}
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="6" lg="4">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h5">{{ t('auth.verify_email.title') }}</v-card-title>
          <v-card-subtitle>{{ t('auth.verify_email.subtitle') }}</v-card-subtitle>
          <v-card-text>
            <v-form @submit.prevent="submit">
              <v-text-field
                v-model="code"
                :label="t('auth.verify_email.code')"
                inputmode="numeric"
                maxlength="6"
                required
              />
              <v-alert v-if="apiError" type="error" class="mb-2">{{ apiError }}</v-alert>
              <v-alert v-if="info" type="success" class="mb-2">{{ info }}</v-alert>
              <v-btn
                type="submit"
                color="primary"
                block
                :loading="submitting"
                :disabled="!canSubmit"
              >
                {{ t('auth.verify_email.submit') }}
              </v-btn>
              <v-btn
                variant="text"
                block
                class="mt-2"
                :loading="resending"
                @click="resend"
              >
                {{ t('auth.verify_email.resend') }}
              </v-btn>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
