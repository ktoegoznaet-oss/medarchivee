<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { authApi, type RegistrationMode } from '@/api/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const form = reactive({
  email: '',
  username: '',
  password: '',
  password_confirm: '',
  terms_accepted: false,
  privacy_accepted: false,
  medical_disclaimer_accepted: false,
  invite_code: '',
})

const submitting = ref(false)
const apiError = ref<string | null>(null)
const registrationMode = ref<RegistrationMode | null>(null)
const modeLoadError = ref<boolean>(false)

onMounted(async () => {
  try {
    const resp = await authApi.getRegistrationMode()
    registrationMode.value = resp.data.mode
  } catch {
    modeLoadError.value = true
    // Безопасный фоллбэк: предполагаем invite_only, чтобы поле было видимо
    // и пользователь не получил неожиданный 403 при сабмите.
    registrationMode.value = 'invite_only'
  }
})

const showInviteField = computed(
  () => registrationMode.value === 'invite_only',
)
const registrationClosed = computed(
  () => registrationMode.value === 'closed',
)
const inviteValid = computed(
  () => !showInviteField.value || form.invite_code.trim().length >= 16,
)

const passwordsMatch = computed(
  () => form.password === '' || form.password === form.password_confirm,
)
const passwordLongEnough = computed(() => form.password.length >= 12)
const emailValid = computed(() => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))

const allConsentsAccepted = computed(
  () => form.terms_accepted && form.privacy_accepted && form.medical_disclaimer_accepted,
)

const canSubmit = computed(
  () =>
    !submitting.value &&
    !registrationClosed.value &&
    allConsentsAccepted.value &&
    emailValid.value &&
    form.username.length >= 3 &&
    passwordLongEnough.value &&
    passwordsMatch.value &&
    inviteValid.value,
)

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  apiError.value = null
  try {
    const payload = {
      email: form.email,
      username: form.username,
      password: form.password,
      password_confirm: form.password_confirm,
      terms_accepted: form.terms_accepted,
      privacy_accepted: form.privacy_accepted,
      medical_disclaimer_accepted: form.medical_disclaimer_accepted,
      ...(form.invite_code.trim()
        ? { invite_code: form.invite_code.trim() }
        : {}),
    }
    const created = await auth.register(payload)
    router.push({ name: 'verify-email', query: { user_id: String(created.id) } })
  } catch (err: unknown) {
    apiError.value = mapError(err)
  } finally {
    submitting.value = false
  }
}

function mapError(err: unknown): string {
  const e = err as { response?: { data?: { detail?: string }; status?: number } }
  const detail = e?.response?.data?.detail
  if (detail === 'email_taken') return t('auth.errors.email_taken')
  if (detail === 'username_taken') return t('auth.errors.username_taken')
  if (detail === 'registration_closed') return t('auth.errors.registration_closed')
  if (detail === 'invite_code_required') return t('auth.errors.invite_required')
  if (detail && detail.startsWith('invite_')) return t('auth.errors.invite_invalid')
  if (e?.response?.status === 422) return t('auth.errors.validation_failed')
  return t('auth.errors.generic')
}
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="8" lg="6">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h5">{{ t('auth.register.title') }}</v-card-title>
          <v-card-text>
            <v-alert v-if="registrationClosed" type="warning" class="mb-4">
              {{ t('auth.register.closed_notice') }}
            </v-alert>

            <v-form v-if="!registrationClosed" @submit.prevent="submit">
              <v-text-field
                v-if="showInviteField"
                v-model="form.invite_code"
                :label="t('auth.register.invite_code')"
                :hint="t('auth.register.invite_hint')"
                persistent-hint
                autocomplete="off"
                required
              />
              <v-text-field
                v-model="form.email"
                :label="t('auth.register.email')"
                type="email"
                autocomplete="email"
                :error="form.email.length > 0 && !emailValid"
                required
              />
              <v-text-field
                v-model="form.username"
                :label="t('auth.register.username')"
                autocomplete="username"
                :hint="t('auth.register.username_hint')"
                persistent-hint
                required
              />
              <v-text-field
                v-model="form.password"
                :label="t('auth.register.password')"
                type="password"
                autocomplete="new-password"
                :hint="t('auth.register.password_requirements')"
                persistent-hint
                :error="form.password.length > 0 && !passwordLongEnough"
                required
              />
              <v-text-field
                v-model="form.password_confirm"
                :label="t('auth.register.password_confirm')"
                type="password"
                autocomplete="new-password"
                :error="form.password_confirm.length > 0 && !passwordsMatch"
                :error-messages="
                  !passwordsMatch ? [t('auth.errors.password_mismatch')] : []
                "
                required
              />

              <v-checkbox
                v-model="form.terms_accepted"
                :label="t('auth.register.terms_label')"
                density="compact"
              />
              <v-checkbox
                v-model="form.privacy_accepted"
                :label="t('auth.register.privacy_label')"
                density="compact"
              />
              <v-checkbox
                v-model="form.medical_disclaimer_accepted"
                :label="t('auth.register.medical_disclaimer_label')"
                density="compact"
              />

              <v-alert v-if="apiError" type="error" class="mb-4">{{ apiError }}</v-alert>

              <v-btn
                type="submit"
                color="primary"
                block
                :loading="submitting"
                :disabled="!canSubmit"
              >
                {{ t('auth.register.submit') }}
              </v-btn>
              <div class="text-center mt-4">
                <router-link to="/auth/login">{{ t('auth.register.have_account') }}</router-link>
              </div>
            </v-form>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
