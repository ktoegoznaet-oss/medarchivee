<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { recoveryApi } from '@/api/recovery'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  email_or_username: '',
  password: '',
  remember_me: false,
})

const submitting = ref(false)
const apiError = ref<string | null>(null)

const canSubmit = computed(
  () => !submitting.value && form.email_or_username.length > 0 && form.password.length > 0,
)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  apiError.value = null
  try {
    await auth.login({ ...form })
    // Если у пользователя ещё нет recovery-фразы — после первого логина
    // ведём его на страницу настройки. Это обязательный шаг (см. Шаг F).
    try {
      const status = await recoveryApi.status()
      if (!status.data.recovery_phrase_set) {
        router.push({ name: 'recovery-phrase' })
        return
      }
    } catch {
      // если /recovery/status не отвечает — просто идём на home
    }
    router.push({ name: 'home' })
  } catch (err: unknown) {
    apiError.value = mapError(err)
  } finally {
    submitting.value = false
  }
}

function mapError(err: unknown): string {
  const e = err as { response?: { data?: { detail?: string }; status?: number } }
  const detail = e?.response?.data?.detail
  if (detail === 'invalid_credentials') return t('auth.errors.invalid_credentials')
  if (detail === 'email_not_verified') return t('auth.errors.email_not_verified')
  if (detail === 'account_inactive') return t('auth.errors.account_inactive')
  if (e?.response?.status === 429) return t('auth.errors.too_many_attempts')
  return t('auth.errors.generic')
}
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="6" lg="4">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h5">{{ t('auth.login.title') }}</v-card-title>
          <v-card-text>
            <v-form @submit.prevent="submit">
              <v-text-field
                v-model="form.email_or_username"
                :label="t('auth.login.email_or_username')"
                autocomplete="username"
                required
              />
              <v-text-field
                v-model="form.password"
                :label="t('auth.login.password')"
                type="password"
                autocomplete="current-password"
                required
              />
              <v-checkbox
                v-model="form.remember_me"
                :label="t('auth.login.remember_me')"
                density="compact"
              />
              <v-alert v-if="apiError" type="error" class="mb-2">{{ apiError }}</v-alert>
              <v-btn
                type="submit"
                color="primary"
                block
                :loading="submitting"
                :disabled="!canSubmit"
              >
                {{ t('auth.login.submit') }}
              </v-btn>
              <div class="d-flex justify-space-between mt-4">
                <router-link to="/auth/register">{{ t('auth.login.no_account') }}</router-link>
                <router-link to="/auth/forgot-password">
                  {{ t('auth.login.forgot_password') }}
                </router-link>
              </div>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
