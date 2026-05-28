<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ticketsApi, type TicketDetail } from '@/api/tickets'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const ticketId = computed(() => Number(route.params.id))
const ticket = ref<TicketDetail | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

const newComment = ref('')
const submittingComment = ref(false)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const resp = await ticketsApi.get(ticketId.value)
    ticket.value = resp.data
  } catch {
    error.value = t('tickets.errors.load_failed')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function submitComment(): Promise<void> {
  if (!newComment.value.trim()) return
  submittingComment.value = true
  try {
    await ticketsApi.addComment(ticketId.value, newComment.value.trim())
    newComment.value = ''
    await load()
  } finally {
    submittingComment.value = false
  }
}

function statusLabel(status: string): string {
  return t(`tickets.status.${status}`)
}

function typeLabel(type: string): string {
  return t(`tickets.types.${type}`)
}
</script>

<template>
  <v-container>
    <v-progress-circular v-if="loading" indeterminate color="primary" />
    <v-alert v-else-if="error" type="error">{{ error }}</v-alert>
    <template v-else-if="ticket">
      <v-card>
        <v-card-title>
          <v-btn variant="text" icon @click="router.push({ name: 'tickets-list' })">
            <v-icon>$prev</v-icon>
          </v-btn>
          {{ ticket.title }}
        </v-card-title>
        <v-card-subtitle>
          <v-chip size="small" class="mr-2">{{ typeLabel(ticket.type) }}</v-chip>
          <v-chip size="small" color="primary">{{ statusLabel(ticket.status) }}</v-chip>
          <span class="ml-3 text-caption">
            {{ new Date(ticket.created_at).toLocaleString('ru-RU') }}
          </span>
        </v-card-subtitle>
        <v-card-text>
          <div class="mb-4" style="white-space: pre-wrap;">{{ ticket.description }}</div>
          <div v-if="ticket.attachments.length > 0">
            <p class="text-caption mb-2">{{ t('tickets.detail.attachments') }}</p>
            <a
              v-for="att in ticket.attachments"
              :key="att.id"
              :href="ticketsApi.attachmentUrl(ticket.id, att.id)"
              target="_blank"
              class="d-block mb-1"
            >
              {{ att.original_filename }} ({{ Math.round(att.size_bytes / 1024) }} КБ)
            </a>
          </div>
        </v-card-text>
      </v-card>

      <v-card class="mt-4">
        <v-card-title>{{ t('tickets.detail.comments') }}</v-card-title>
        <v-card-text>
          <v-list v-if="ticket.comments.length > 0">
            <v-list-item v-for="comment in ticket.comments" :key="comment.id">
              <v-list-item-subtitle>
                {{ new Date(comment.created_at).toLocaleString('ru-RU') }}
                <span
                  v-if="comment.author_user_id !== ticket.user_id"
                  class="ml-2 text-primary"
                >
                  {{ t('tickets.detail.admin_reply') }}
                </span>
              </v-list-item-subtitle>
              <v-list-item-title style="white-space: pre-wrap;">
                {{ comment.body }}
              </v-list-item-title>
            </v-list-item>
          </v-list>
          <p v-else class="text-disabled">{{ t('tickets.detail.no_comments') }}</p>

          <v-divider class="my-4" />

          <v-textarea
            v-model="newComment"
            :label="t('tickets.detail.add_comment')"
            rows="3"
            auto-grow
            :disabled="ticket.status === 'rejected' || ticket.status === 'resolved'"
          />
          <v-btn
            color="primary"
            :loading="submittingComment"
            :disabled="!newComment.trim() || ticket.status === 'rejected' || ticket.status === 'resolved'"
            @click="submitComment"
          >
            {{ t('tickets.detail.submit_comment') }}
          </v-btn>
        </v-card-text>
      </v-card>
    </template>
  </v-container>
</template>
