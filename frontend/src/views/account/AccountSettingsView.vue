<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { meApi } from '@/api/me'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const exporting = ref(false)
const exportError = ref<string | null>(null)

const deleteDialog = ref(false)
const deletePassword = ref('')
const deleteAck = ref(false)
const deleting = ref(false)
const deleteError = ref<string | null>(null)

async function downloadExport(): Promise<void> {
  exporting.value = true
  exportError.value = null
  try {
    const blob = await meApi.downloadExport()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `medarchive-export-${auth.user?.username ?? 'me'}.zip`
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    exportError.value = t('account.export.failed')
  } finally {
    exporting.value = false
  }
}

async function deleteAccount(): Promise<void> {
  deleting.value = true
  deleteError.value = null
  try {
    await meApi.deleteAccount(deletePassword.value)
    deleteDialog.value = false
    // Аккаунт удалён, backend invalidate'нул refresh-token. Logout
    // может упасть с 401 (cookie уже невалиден) — это ожидаемо,
    // главное сбросить локальный access_token до редиректа.
    await auth.logout().catch(() => {})
    router.push({ name: 'register' })
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    if (e?.response?.data?.detail === 'invalid_password') {
      deleteError.value = t('account.delete.wrong_password')
    } else {
      deleteError.value = t('account.delete.failed')
    }
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <v-container>
    <v-card class="mb-4">
      <v-card-title>{{ t('account.export.title') }}</v-card-title>
      <v-card-text>
        <p class="mb-2">{{ t('account.export.intro') }}</p>
        <v-alert v-if="exportError" type="error" class="mb-2">
          {{ exportError }}
        </v-alert>
        <v-btn color="primary" :loading="exporting" @click="downloadExport">
          {{ t('account.export.button') }}
        </v-btn>
      </v-card-text>
    </v-card>

    <v-card>
      <v-card-title class="text-error">{{ t('account.delete.title') }}</v-card-title>
      <v-card-text>
        <v-alert type="error" class="mb-2">
          {{ t('account.delete.warning') }}
        </v-alert>
        <v-btn color="error" variant="outlined" @click="deleteDialog = true">
          {{ t('account.delete.button') }}
        </v-btn>
      </v-card-text>
    </v-card>

    <v-dialog v-model="deleteDialog" max-width="500" persistent>
      <v-card>
        <v-card-title class="text-error">{{ t('account.delete.confirm_title') }}</v-card-title>
        <v-card-text>
          <p class="mb-3">{{ t('account.delete.confirm_text') }}</p>
          <v-text-field
            v-model="deletePassword"
            :label="t('account.delete.password')"
            type="password"
            autocomplete="current-password"
          />
          <v-checkbox
            v-model="deleteAck"
            :label="t('account.delete.ack')"
            density="compact"
          />
          <v-alert v-if="deleteError" type="error" class="mb-2">
            {{ deleteError }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="deleteDialog = false">{{ t('common.cancel') }}</v-btn>
          <v-btn
            color="error"
            :loading="deleting"
            :disabled="!deletePassword || !deleteAck"
            @click="deleteAccount"
          >
            {{ t('account.delete.confirm_button') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
