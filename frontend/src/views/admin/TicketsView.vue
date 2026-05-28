<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi } from '@/api/admin'
import type { Ticket, TicketDetail, TicketStatus, TicketType } from '@/api/tickets'

const { t } = useI18n()

const tickets = ref<Ticket[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const statusFilter = ref<TicketStatus | undefined>(undefined)
const typeFilter = ref<TicketType | undefined>(undefined)
const selected = ref<TicketDetail | null>(null)
const newComment = ref('')
const isInternal = ref(false)
const submittingComment = ref(false)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const resp = await adminApi.listTickets(statusFilter.value, typeFilter.value)
    tickets.value = resp.data.tickets
  } catch {
    error.value = t('admin.errors.load_failed')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([statusFilter, typeFilter], load)

async function open(ticket: Ticket): Promise<void> {
  try {
    const resp = await adminApi.getTicket(ticket.id)
    selected.value = resp.data
  } catch {
    // ignore
  }
}

async function changeStatus(status: TicketStatus): Promise<void> {
  if (!selected.value) return
  try {
    await adminApi.setTicketStatus(selected.value.id, status)
    await load()
    const resp = await adminApi.getTicket(selected.value.id)
    selected.value = resp.data
  } catch {
    // ignore
  }
}

async function addComment(): Promise<void> {
  if (!selected.value || !newComment.value.trim()) return
  submittingComment.value = true
  try {
    await adminApi.addTicketComment(
      selected.value.id,
      newComment.value.trim(),
      isInternal.value,
    )
    newComment.value = ''
    isInternal.value = false
    const resp = await adminApi.getTicket(selected.value.id)
    selected.value = resp.data
  } finally {
    submittingComment.value = false
  }
}

function statusColor(status: string): string {
  return {
    new: 'info',
    in_progress: 'warning',
    resolved: 'success',
    rejected: 'error',
  }[status] ?? 'grey'
}
</script>

<template>
  <v-card-text>
    <v-row class="mb-2">
      <v-col cols="12" sm="6">
        <v-select
          v-model="statusFilter"
          :label="t('admin.tickets.filter_status')"
          :items="[
            { title: t('admin.tickets.all'), value: undefined },
            { title: t('tickets.status.new'), value: 'new' },
            { title: t('tickets.status.in_progress'), value: 'in_progress' },
            { title: t('tickets.status.resolved'), value: 'resolved' },
            { title: t('tickets.status.rejected'), value: 'rejected' },
          ]"
          density="compact"
          clearable
        />
      </v-col>
      <v-col cols="12" sm="6">
        <v-select
          v-model="typeFilter"
          :label="t('admin.tickets.filter_type')"
          :items="[
            { title: t('admin.tickets.all'), value: undefined },
            { title: t('tickets.types.bug'), value: 'bug' },
            { title: t('tickets.types.suggestion'), value: 'suggestion' },
            { title: t('tickets.types.question'), value: 'question' },
            { title: t('tickets.types.other'), value: 'other' },
          ]"
          density="compact"
          clearable
        />
      </v-col>
    </v-row>

    <v-progress-circular v-if="loading" indeterminate color="primary" />
    <v-alert v-else-if="error" type="error">{{ error }}</v-alert>
    <v-table v-else density="compact">
      <thead>
        <tr>
          <th>{{ t('admin.tickets.status') }}</th>
          <th>{{ t('admin.tickets.type') }}</th>
          <th>{{ t('admin.tickets.title') }}</th>
          <th>{{ t('admin.tickets.user') }}</th>
          <th>{{ t('admin.tickets.updated') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="ticket in tickets"
          :key="ticket.id"
          style="cursor: pointer"
          @click="open(ticket)"
        >
          <td>
            <v-chip size="x-small" :color="statusColor(ticket.status)">
              {{ t(`tickets.status.${ticket.status}`) }}
            </v-chip>
          </td>
          <td class="text-caption">{{ t(`tickets.types.${ticket.type}`) }}</td>
          <td>{{ ticket.title }}</td>
          <td class="text-caption">{{ ticket.user_email ?? `#${ticket.user_id}` }}</td>
          <td class="text-caption">
            {{ new Date(ticket.updated_at).toLocaleString('ru-RU') }}
          </td>
        </tr>
      </tbody>
    </v-table>

    <v-dialog v-model="selected" max-width="800">
      <v-card v-if="selected">
        <v-card-title>
          {{ selected.title }}
          <v-chip
            size="small"
            class="ml-2"
            :color="statusColor(selected.status)"
          >
            {{ t(`tickets.status.${selected.status}`) }}
          </v-chip>
        </v-card-title>
        <v-card-subtitle>
          {{ selected.user_email ?? `#${selected.user_id}` }} ·
          {{ new Date(selected.created_at).toLocaleString('ru-RU') }}
        </v-card-subtitle>
        <v-card-text>
          <div class="mb-4" style="white-space: pre-wrap;">{{ selected.description }}</div>
          <div v-if="selected.url" class="text-caption text-disabled">
            URL: {{ selected.url }}
          </div>
          <div v-if="selected.user_agent" class="text-caption text-disabled">
            UA: {{ selected.user_agent }}
          </div>
          <div v-if="selected.screen_size" class="text-caption text-disabled">
            Screen: {{ selected.screen_size }}
          </div>

          <div v-if="selected.attachments.length > 0" class="mt-2">
            <p class="text-caption">{{ t('admin.tickets.attachments') }}</p>
            <a
              v-for="att in selected.attachments"
              :key="att.id"
              :href="`/api/v1/tickets/${selected.id}/attachments/${att.id}`"
              target="_blank"
              class="d-block"
            >
              {{ att.original_filename }}
            </a>
          </div>

          <v-divider class="my-4" />

          <div class="mb-2 text-subtitle-2">{{ t('admin.tickets.change_status') }}</div>
          <v-btn-group density="compact">
            <v-btn size="small" @click="changeStatus('new')">{{ t('tickets.status.new') }}</v-btn>
            <v-btn size="small" @click="changeStatus('in_progress')">{{ t('tickets.status.in_progress') }}</v-btn>
            <v-btn size="small" color="success" @click="changeStatus('resolved')">{{ t('tickets.status.resolved') }}</v-btn>
            <v-btn size="small" color="error" @click="changeStatus('rejected')">{{ t('tickets.status.rejected') }}</v-btn>
          </v-btn-group>

          <v-divider class="my-4" />

          <div class="text-subtitle-2 mb-2">{{ t('admin.tickets.comments') }}</div>
          <v-list density="compact">
            <v-list-item
              v-for="c in selected.comments"
              :key="c.id"
              :class="c.is_internal ? 'bg-grey-lighten-3' : ''"
            >
              <v-list-item-subtitle>
                {{ new Date(c.created_at).toLocaleString('ru-RU') }}
                <v-chip v-if="c.is_internal" size="x-small" color="grey" class="ml-2">
                  {{ t('admin.tickets.internal') }}
                </v-chip>
              </v-list-item-subtitle>
              <v-list-item-title style="white-space: pre-wrap;">
                {{ c.body }}
              </v-list-item-title>
            </v-list-item>
          </v-list>

          <v-textarea
            v-model="newComment"
            :label="t('admin.tickets.add_comment')"
            rows="3"
            auto-grow
          />
          <v-checkbox
            v-model="isInternal"
            :label="t('admin.tickets.internal_only')"
            density="compact"
          />
          <v-btn
            color="primary"
            :loading="submittingComment"
            :disabled="!newComment.trim()"
            @click="addComment"
          >
            {{ t('admin.tickets.submit_comment') }}
          </v-btn>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="selected = null">{{ t('common.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card-text>
</template>
