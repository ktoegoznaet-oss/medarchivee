<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi, type Invite } from '@/api/admin'

const { t } = useI18n()

const invites = ref<Invite[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const note = ref('')
const creating = ref(false)
const newCode = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const resp = await adminApi.listInvites()
    invites.value = resp.data.invites
  } catch {
    error.value = t('admin.errors.load_failed')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function create(): Promise<void> {
  creating.value = true
  try {
    const resp = await adminApi.createInvite(note.value.trim() || undefined)
    newCode.value = resp.data.invite.code
    note.value = ''
    await load()
  } finally {
    creating.value = false
  }
}

async function revoke(invite: Invite): Promise<void> {
  if (!confirm(t('admin.invites.confirm_revoke'))) return
  try {
    await adminApi.revokeInvite(invite.id)
    await load()
  } catch {
    // ignore — кнопка просто не отреагирует
  }
}

function statusColor(status: string): string {
  return {
    active: 'success',
    used: 'info',
    revoked: 'error',
    expired: 'warning',
  }[status] ?? 'grey'
}

async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // ignore
  }
}
</script>

<template>
  <v-card-text>
    <v-row class="mb-4">
      <v-col cols="12" md="8">
        <v-text-field
          v-model="note"
          :label="t('admin.invites.note_label')"
          :hint="t('admin.invites.note_hint')"
          persistent-hint
          density="compact"
        />
      </v-col>
      <v-col cols="12" md="4">
        <v-btn color="primary" :loading="creating" block @click="create">
          {{ t('admin.invites.create') }}
        </v-btn>
      </v-col>
    </v-row>

    <v-alert
      v-if="newCode"
      type="success"
      closable
      class="mb-4"
      @click:close="newCode = null"
    >
      <div>{{ t('admin.invites.new_code_created') }}:</div>
      <code class="text-h6">{{ newCode }}</code>
      <v-btn
        size="small"
        variant="text"
        class="ml-2"
        @click="copyToClipboard(newCode!)"
      >
        {{ t('common.copy') }}
      </v-btn>
    </v-alert>

    <v-progress-circular v-if="loading" indeterminate color="primary" />
    <v-alert v-else-if="error" type="error">{{ error }}</v-alert>
    <v-table v-else density="compact">
      <thead>
        <tr>
          <th>{{ t('admin.invites.code') }}</th>
          <th>{{ t('admin.invites.status') }}</th>
          <th>{{ t('admin.invites.note') }}</th>
          <th>{{ t('admin.invites.created') }}</th>
          <th>{{ t('admin.invites.used_by') }}</th>
          <th>{{ t('admin.invites.actions') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="invite in invites" :key="invite.id">
          <td>
            <code>{{ invite.code }}</code>
            <v-btn
              size="x-small"
              variant="text"
              icon="mdi-content-copy"
              @click="copyToClipboard(invite.code)"
            />
          </td>
          <td>
            <v-chip size="small" :color="statusColor(invite.status)">
              {{ invite.status }}
            </v-chip>
          </td>
          <td>{{ invite.note ?? '—' }}</td>
          <td class="text-caption">
            {{ new Date(invite.created_at).toLocaleDateString('ru-RU') }}
          </td>
          <td class="text-caption">{{ invite.used_by_email ?? '—' }}</td>
          <td>
            <v-btn
              v-if="invite.status === 'active'"
              size="x-small"
              color="error"
              variant="text"
              @click="revoke(invite)"
            >
              {{ t('admin.invites.revoke') }}
            </v-btn>
          </td>
        </tr>
      </tbody>
    </v-table>
  </v-card-text>
</template>
