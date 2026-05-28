<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi, type AdminUser, type UserRole, type UserStatus } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const users = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')
const actionError = ref<string | null>(null)

let searchTimer: number | null = null

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const resp = await adminApi.listUsers(search.value)
    users.value = resp.data.users
    total.value = resp.data.total
  } catch {
    error.value = t('admin.errors.load_failed')
  } finally {
    loading.value = false
  }
}

onMounted(load)

watch(search, () => {
  if (searchTimer) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(load, 300)
})

async function setStatus(user: AdminUser, status: UserStatus): Promise<void> {
  actionError.value = null
  try {
    const resp = await adminApi.setUserStatus(user.id, status)
    user.status = resp.data.status
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    if (e?.response?.data?.detail === 'cannot_block_self') {
      actionError.value = t('admin.users.cannot_block_self')
    } else {
      actionError.value = t('admin.errors.action_failed')
    }
  }
}

async function setRole(user: AdminUser, role: UserRole): Promise<void> {
  actionError.value = null
  try {
    const resp = await adminApi.setUserRole(user.id, role)
    user.role = resp.data.role
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    if (e?.response?.data?.detail === 'last_admin_demotion_forbidden') {
      actionError.value = t('admin.users.last_admin')
    } else {
      actionError.value = t('admin.errors.action_failed')
    }
  }
}
</script>

<template>
  <v-card-text>
    <v-text-field
      v-model="search"
      :label="t('admin.users.search')"
      prepend-inner-icon="mdi-magnify"
      density="compact"
      clearable
    />
    <v-alert v-if="actionError" type="error" closable @click:close="actionError = null">
      {{ actionError }}
    </v-alert>

    <v-progress-circular v-if="loading" indeterminate color="primary" />
    <v-alert v-else-if="error" type="error">{{ error }}</v-alert>
    <div v-else>
      <p class="text-caption mb-2">{{ t('admin.users.total', { n: total }) }}</p>
      <v-table density="compact">
        <thead>
          <tr>
            <th>{{ t('admin.users.email') }}</th>
            <th>{{ t('admin.users.username') }}</th>
            <th>{{ t('admin.users.role') }}</th>
            <th>{{ t('admin.users.status') }}</th>
            <th>{{ t('admin.users.created') }}</th>
            <th>{{ t('admin.users.last_login') }}</th>
            <th>{{ t('admin.users.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>{{ user.email }}</td>
            <td>{{ user.username }}</td>
            <td>
              <v-chip
                size="small"
                :color="user.role === 'admin' ? 'primary' : 'default'"
              >
                {{ user.role }}
              </v-chip>
            </td>
            <td>
              <v-chip
                size="small"
                :color="user.status === 'active' ? 'success' : 'error'"
              >
                {{ user.status }}
              </v-chip>
            </td>
            <td class="text-caption">
              {{ new Date(user.created_at).toLocaleDateString('ru-RU') }}
            </td>
            <td class="text-caption">
              {{ user.last_login_at ? new Date(user.last_login_at).toLocaleDateString('ru-RU') : '—' }}
            </td>
            <td>
              <v-menu>
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    size="x-small"
                    icon="mdi-dots-vertical"
                    variant="text"
                  />
                </template>
                <v-list density="compact">
                  <v-list-item
                    v-if="user.status === 'active'"
                    :disabled="user.id === auth.user?.id"
                    @click="setStatus(user, 'blocked')"
                  >
                    <v-list-item-title>{{ t('admin.users.block') }}</v-list-item-title>
                  </v-list-item>
                  <v-list-item
                    v-else
                    @click="setStatus(user, 'active')"
                  >
                    <v-list-item-title>{{ t('admin.users.unblock') }}</v-list-item-title>
                  </v-list-item>
                  <v-list-item
                    v-if="user.role === 'user'"
                    @click="setRole(user, 'admin')"
                  >
                    <v-list-item-title>{{ t('admin.users.make_admin') }}</v-list-item-title>
                  </v-list-item>
                  <v-list-item
                    v-else
                    :disabled="user.id === auth.user?.id"
                    @click="setRole(user, 'user')"
                  >
                    <v-list-item-title>{{ t('admin.users.remove_admin') }}</v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-menu>
            </td>
          </tr>
        </tbody>
      </v-table>
    </div>
  </v-card-text>
</template>
