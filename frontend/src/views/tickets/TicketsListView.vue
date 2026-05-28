<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ticketsApi, type Ticket } from '@/api/tickets'

const { t } = useI18n()
const router = useRouter()

const tickets = ref<Ticket[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    const resp = await ticketsApi.listMine()
    tickets.value = resp.data.tickets
  } catch {
    error.value = t('tickets.errors.load_failed')
  } finally {
    loading.value = false
  }
})

function statusColor(status: string): string {
  return {
    new: 'info',
    in_progress: 'warning',
    resolved: 'success',
    rejected: 'error',
  }[status] ?? 'grey'
}

function statusLabel(status: string): string {
  return t(`tickets.status.${status}`)
}

function typeLabel(type: string): string {
  return t(`tickets.types.${type}`)
}

function openTicket(id: number): void {
  router.push({ name: 'ticket-detail', params: { id } })
}
</script>

<template>
  <v-container>
    <v-card>
      <v-card-title class="text-h5">{{ t('tickets.list.title') }}</v-card-title>
      <v-card-text>
        <v-progress-circular v-if="loading" indeterminate color="primary" />
        <v-alert v-else-if="error" type="error">{{ error }}</v-alert>
        <v-alert v-else-if="tickets.length === 0" type="info">
          {{ t('tickets.list.empty') }}
        </v-alert>
        <v-list v-else>
          <v-list-item
            v-for="ticket in tickets"
            :key="ticket.id"
            @click="openTicket(ticket.id)"
          >
            <template #prepend>
              <v-chip :color="statusColor(ticket.status)" size="small" class="mr-3">
                {{ statusLabel(ticket.status) }}
              </v-chip>
            </template>
            <v-list-item-title>
              <span class="text-caption text-disabled mr-2">
                {{ typeLabel(ticket.type) }}
              </span>
              {{ ticket.title }}
            </v-list-item-title>
            <v-list-item-subtitle>
              {{ new Date(ticket.updated_at).toLocaleString('ru-RU') }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>
    </v-card>
  </v-container>
</template>
