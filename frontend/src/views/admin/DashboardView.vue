<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi, type DashboardStats } from '@/api/admin'

const { t } = useI18n()
const stats = ref<DashboardStats | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    const resp = await adminApi.dashboard()
    stats.value = resp.data
  } catch {
    error.value = t('admin.errors.load_failed')
  } finally {
    loading.value = false
  }
})

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} ГБ`
}
</script>

<template>
  <v-card-text>
    <v-progress-circular v-if="loading" indeterminate color="primary" />
    <v-alert v-else-if="error" type="error">{{ error }}</v-alert>
    <div v-else-if="stats">
      <v-row>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.users_total') }}</div>
            <div class="text-h4">{{ stats.users_total }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.users_active_7d') }}</div>
            <div class="text-h4 text-success">{{ stats.users_active_7d }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.users_new_7d') }}</div>
            <div class="text-h4 text-primary">{{ stats.users_new_7d }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.users_blocked') }}</div>
            <div class="text-h4 text-error">{{ stats.users_blocked }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.users_active_30d') }}</div>
            <div class="text-h4">{{ stats.users_active_30d }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.tickets_new') }}</div>
            <div class="text-h4 text-warning">{{ stats.tickets_new }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.tickets_total') }}</div>
            <div class="text-h4">{{ stats.tickets_total }}</div>
          </v-card>
        </v-col>
        <v-col cols="12" sm="6" md="3">
          <v-card variant="outlined" class="pa-4">
            <div class="text-caption text-disabled">{{ t('admin.dashboard.uploads_size') }}</div>
            <div class="text-h4">{{ formatBytes(stats.uploads_size_bytes) }}</div>
          </v-card>
        </v-col>
      </v-row>

      <v-card variant="outlined" class="mt-6 pa-4">
        <div class="text-subtitle-1 mb-2">{{ t('admin.dashboard.registrations_30d') }}</div>
        <div v-if="stats.activity_by_day.length === 0" class="text-disabled">
          {{ t('admin.dashboard.no_activity') }}
        </div>
        <table v-else class="activity-table">
          <tr v-for="row in stats.activity_by_day" :key="row.date">
            <td class="text-caption">{{ row.date }}</td>
            <td>
              <div
                class="activity-bar"
                :style="{ width: Math.min(row.count * 20, 200) + 'px' }"
              />
            </td>
            <td class="text-caption">{{ row.count }}</td>
          </tr>
        </table>
      </v-card>
    </div>
  </v-card-text>
</template>

<style scoped>
.activity-table {
  width: 100%;
  border-collapse: collapse;
}
.activity-table td {
  padding: 4px 8px;
}
.activity-bar {
  background: rgb(var(--v-theme-primary));
  height: 16px;
  border-radius: 2px;
  min-width: 4px;
}
</style>
