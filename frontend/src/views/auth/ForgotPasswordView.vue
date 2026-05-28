<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { recoveryApi } from '@/api/recovery'

const { t } = useI18n()
const router = useRouter()

type Tab = 'phrase' | 'no-phrase'
const tab = ref<Tab>('phrase')

// --- "У меня есть фраза" ---
const phraseForm = ref({
  email: '',
  phrase: '',
  new_password: '',
  new_password_confirm: '',
})
const phraseError = ref<string | null>(null)
const phraseSubmitting = ref(false)
const phrasePasswordsMatch = computed(
  () =>
    phraseForm.value.new_password === '' ||
    phraseForm.value.new_password === phraseForm.value.new_password_confirm,
)
const phraseCanSubmit = computed(
  () =>
    !phraseSubmitting.value &&
    phraseForm.value.email.length > 0 &&
    phraseForm.value.phrase.trim().split(/\s+/).length === 12 &&
    phraseForm.value.new_password.length >= 12 &&
    phrasePasswordsMatch.value,
)

async function submitPhraseReset(): Promise<void> {
  if (!phraseCanSubmit.value) return
  phraseSubmitting.value = true
  phraseError.value = null
  try {
    await recoveryApi.resetPassword({
      email: phraseForm.value.email,
      phrase: phraseForm.value.phrase.trim(),
      new_password: phraseForm.value.new_password,
      new_password_confirm: phraseForm.value.new_password_confirm,
    })
    router.push({ name: 'login', query: { reset: '1' } })
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    if (e?.response?.data?.detail === 'phrase_invalid') {
      phraseError.value = t('recovery.forgot.errors.phrase_invalid')
    } else {
      phraseError.value = t('recovery.forgot.errors.generic')
    }
  } finally {
    phraseSubmitting.value = false
  }
}

// --- "У меня нет фразы" — wipe ---
type WipeStep = 'request' | 'confirm' | 'done'
const wipeStep = ref<WipeStep>('request')
const wipeEmail = ref('')
const wipeCode = ref('')
const wipeError = ref<string | null>(null)
const wipeSubmitting = ref(false)
const wipeAcknowledged = ref(false)

async function submitWipeRequest(): Promise<void> {
  wipeError.value = null
  wipeSubmitting.value = true
  try {
    await recoveryApi.requestWipe(wipeEmail.value)
    wipeStep.value = 'confirm'
  } catch {
    wipeError.value = t('recovery.forgot.errors.generic')
  } finally {
    wipeSubmitting.value = false
  }
}

async function submitWipeConfirm(): Promise<void> {
  wipeError.value = null
  wipeSubmitting.value = true
  try {
    await recoveryApi.confirmWipe(wipeEmail.value, wipeCode.value)
    wipeStep.value = 'done'
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    if (e?.response?.data?.detail === 'wipe_code_invalid') {
      wipeError.value = t('recovery.forgot.errors.wipe_code_invalid')
    } else {
      wipeError.value = t('recovery.forgot.errors.generic')
    }
  } finally {
    wipeSubmitting.value = false
  }
}
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="8" lg="6">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h5">{{ t('recovery.forgot.title') }}</v-card-title>
          <v-card-text>
            <v-tabs v-model="tab" align-tabs="center" class="mb-4">
              <v-tab value="phrase">{{ t('recovery.forgot.tab_have_phrase') }}</v-tab>
              <v-tab value="no-phrase">{{ t('recovery.forgot.tab_no_phrase') }}</v-tab>
            </v-tabs>

            <v-window v-model="tab">
              <!-- Tab 1: have phrase -->
              <v-window-item value="phrase">
                <p class="mb-4">{{ t('recovery.forgot.phrase_intro') }}</p>
                <v-form @submit.prevent="submitPhraseReset">
                  <v-text-field
                    v-model="phraseForm.email"
                    :label="t('recovery.forgot.email')"
                    type="email"
                    autocomplete="email"
                    required
                  />
                  <v-textarea
                    v-model="phraseForm.phrase"
                    :label="t('recovery.forgot.phrase')"
                    :hint="t('recovery.forgot.phrase_hint')"
                    persistent-hint
                    rows="3"
                    auto-grow
                  />
                  <v-text-field
                    v-model="phraseForm.new_password"
                    :label="t('recovery.forgot.new_password')"
                    type="password"
                    autocomplete="new-password"
                    :hint="t('auth.register.password_requirements')"
                    persistent-hint
                  />
                  <v-text-field
                    v-model="phraseForm.new_password_confirm"
                    :label="t('recovery.forgot.new_password_confirm')"
                    type="password"
                    autocomplete="new-password"
                    :error="
                      phraseForm.new_password_confirm.length > 0 &&
                      !phrasePasswordsMatch
                    "
                  />
                  <v-alert v-if="phraseError" type="error" class="mb-4">
                    {{ phraseError }}
                  </v-alert>
                  <v-btn
                    type="submit"
                    color="primary"
                    block
                    :loading="phraseSubmitting"
                    :disabled="!phraseCanSubmit"
                  >
                    {{ t('recovery.forgot.submit_reset') }}
                  </v-btn>
                </v-form>
              </v-window-item>

              <!-- Tab 2: no phrase → wipe -->
              <v-window-item value="no-phrase">
                <v-alert type="error" class="mb-4">
                  {{ t('recovery.forgot.no_phrase_warning') }}
                </v-alert>

                <div v-if="wipeStep === 'request'">
                  <v-text-field
                    v-model="wipeEmail"
                    :label="t('recovery.forgot.email')"
                    type="email"
                    autocomplete="email"
                  />
                  <v-checkbox
                    v-model="wipeAcknowledged"
                    :label="t('recovery.forgot.wipe_ack')"
                    density="compact"
                  />
                  <v-alert v-if="wipeError" type="error" class="mb-4">
                    {{ wipeError }}
                  </v-alert>
                  <v-btn
                    color="error"
                    block
                    :loading="wipeSubmitting"
                    :disabled="!wipeEmail || !wipeAcknowledged"
                    @click="submitWipeRequest"
                  >
                    {{ t('recovery.forgot.request_wipe_code') }}
                  </v-btn>
                </div>

                <div v-else-if="wipeStep === 'confirm'">
                  <p class="mb-4">{{ t('recovery.forgot.wipe_code_sent') }}</p>
                  <v-text-field
                    v-model="wipeCode"
                    :label="t('recovery.forgot.wipe_code_label')"
                    inputmode="numeric"
                    maxlength="8"
                  />
                  <v-alert v-if="wipeError" type="error" class="mb-4">
                    {{ wipeError }}
                  </v-alert>
                  <v-btn
                    color="error"
                    block
                    :loading="wipeSubmitting"
                    :disabled="wipeCode.length !== 8"
                    @click="submitWipeConfirm"
                  >
                    {{ t('recovery.forgot.confirm_wipe') }}
                  </v-btn>
                </div>

                <div v-else-if="wipeStep === 'done'">
                  <v-alert type="success" class="mb-4">
                    {{ t('recovery.forgot.wipe_done') }}
                  </v-alert>
                  <v-btn color="primary" block @click="router.push({ name: 'register' })">
                    {{ t('recovery.forgot.go_register') }}
                  </v-btn>
                </div>
              </v-window-item>
            </v-window>

            <div class="text-center mt-4">
              <router-link to="/auth/login">{{ t('recovery.forgot.back_login') }}</router-link>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
