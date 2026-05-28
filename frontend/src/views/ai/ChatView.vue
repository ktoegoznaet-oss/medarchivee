<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAIStore } from '@/stores/ai'
import { useAnalysesStore } from '@/stores/analyses'
import AttachDataDialog from '@/components/ai/AttachDataDialog.vue'
import type {
  AIComplexity,
  AITone,
  AttachedData,
} from '@/api/ai'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useAIStore()
const analysesStore = useAnalysesStore()

const messageText = ref('')
const errorMessage = ref<string | null>(null)
const attachDialog = ref(false)
const attached = ref<AttachedData | null>(null)
const overrideTone = ref<AITone | null>(null)
const overrideComplexity = ref<AIComplexity | null>(null)
const drawer = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)

const toneOptions: { value: AITone; labelKey: string }[] = [
  { value: 'close_person', labelKey: 'ai.tone.close_person' },
  { value: 'good_friend', labelKey: 'ai.tone.good_friend' },
  { value: 'funny_colleague', labelKey: 'ai.tone.funny_colleague' },
  { value: 'professional', labelKey: 'ai.tone.professional' },
  { value: 'encyclopedia', labelKey: 'ai.tone.encyclopedia' },
]

const complexityOptions: { value: AIComplexity; labelKey: string }[] = [
  { value: 'child', labelKey: 'ai.complexity.child' },
  { value: 'family_doctor', labelKey: 'ai.complexity.family_doctor' },
  { value: 'professor', labelKey: 'ai.complexity.professor' },
  { value: 'dry_facts', labelKey: 'ai.complexity.dry_facts' },
]

const effectiveTone = computed<AITone>(
  () => overrideTone.value ?? store.settings?.tone ?? 'good_friend',
)
const effectiveComplexity = computed<AIComplexity>(
  () => overrideComplexity.value ?? store.settings?.complexity_level ?? 'family_doctor',
)

const attachedChip = computed(() => {
  if (!attached.value) return null
  const parts: string[] = []
  if (attached.value.include_profile) parts.push(t('ai.attach.preview_profile'))
  if (attached.value.analysis_ids.length > 0) {
    parts.push(
      t(
        'ai.attach.preview_analyses',
        { count: attached.value.analysis_ids.length },
        attached.value.analysis_ids.length,
      ),
    )
  }
  return parts.join(' + ')
})

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

async function ensureSettingsAndList(): Promise<void> {
  if (!store.settings) await store.fetchSettings()
  if (store.conversations.length === 0) await store.fetchConversations()
}

async function startNewConversation(): Promise<void> {
  await store.createConversation()
  messageText.value = ''
  attached.value = null
  overrideTone.value = null
  overrideComplexity.value = null
  errorMessage.value = null
  drawer.value = false
}

async function openConversation(id: number): Promise<void> {
  errorMessage.value = null
  overrideTone.value = null
  overrideComplexity.value = null
  attached.value = null
  messageText.value = ''
  await store.openConversation(id)
  drawer.value = false
  await scrollToBottom()
}

async function send(): Promise<void> {
  if (!messageText.value.trim()) return
  if (!store.currentConversation) {
    await startNewConversation()
  }
  errorMessage.value = null
  try {
    await store.sendMessage({
      message: messageText.value.trim(),
      attached_data: attached.value ?? undefined,
      override_tone:
        overrideTone.value && overrideTone.value !== store.settings?.tone
          ? overrideTone.value
          : undefined,
      override_complexity:
        overrideComplexity.value &&
        overrideComplexity.value !== store.settings?.complexity_level
          ? overrideComplexity.value
          : undefined,
    })
    messageText.value = ''
    attached.value = null
    await scrollToBottom()
  } catch (err) {
    const detail =
      (err as { response?: { data?: { detail?: string } } }).response?.data
        ?.detail ?? null
    errorMessage.value = detail ?? t('ai.errors.generic')
  }
}

async function archive(id: number): Promise<void> {
  await store.archiveConversation(id)
}

onMounted(async () => {
  await ensureSettingsAndList()
  // Поддержка query: ?conversation=ID, или ?analysis_id=N&prefill=Текст —
  // последний вариант приходит с кнопки «Спросить Ивана Иваныча» в анализе.
  const convQ = route.query.conversation
  const prefill = route.query.prefill
  const analysisQ = route.query.analysis_id

  if (typeof convQ === 'string') {
    await openConversation(Number(convQ))
  } else if (typeof prefill === 'string' || typeof analysisQ === 'string') {
    // Готовим новую беседу под предзаполненный сценарий.
    await store.createConversation()
    if (typeof prefill === 'string') {
      messageText.value = prefill
    }
    if (typeof analysisQ === 'string') {
      const id = Number(analysisQ)
      if (!Number.isNaN(id)) {
        if (analysesStore.records.length === 0) await analysesStore.fetchList()
        attached.value = { include_profile: false, analysis_ids: [id] }
      }
    }
  }
  // Чистим query, чтобы при F5 не восстанавливался автозапрос.
  if (Object.keys(route.query).length > 0) {
    router.replace({ name: 'ai-chat' })
  }
  await scrollToBottom()
})

watch(
  () => store.messages.length,
  async () => {
    await scrollToBottom()
  },
)
</script>

<template>
  <v-container fluid class="pa-0 d-flex" style="height: calc(100vh - 64px);">
    <!-- Список бесед: на десктопе — постоянно слева, на мобильном — drawer. -->
    <v-navigation-drawer
      v-model="drawer"
      :permanent="$vuetify.display.mdAndUp"
      width="280"
      class="ai-sidebar"
    >
      <div class="pa-3">
        <v-btn
          color="primary"
          block
          prepend-icon="mdi-plus"
          @click="startNewConversation"
        >
          {{ t('ai.new_conversation') }}
        </v-btn>
      </div>
      <v-divider />
      <v-list density="compact">
        <v-list-item
          v-for="c in store.conversations"
          :key="c.id"
          :title="c.title || t('ai.untitled')"
          :subtitle="c.last_message_preview ?? ''"
          :active="store.currentConversation?.id === c.id"
          @click="openConversation(c.id)"
        >
          <template #append>
            <v-btn
              icon="mdi-archive-outline"
              size="x-small"
              variant="text"
              @click.stop="archive(c.id)"
            />
          </template>
        </v-list-item>
        <v-list-item v-if="store.conversations.length === 0" :title="t('ai.no_conversations')" />
      </v-list>
    </v-navigation-drawer>

    <v-main class="d-flex flex-column" style="min-height: 0;">
      <!-- Шапка чата -->
      <div class="d-flex align-center pa-3 border-b">
        <v-btn
          v-if="$vuetify.display.smAndDown"
          icon="mdi-menu"
          variant="text"
          @click="drawer = !drawer"
        />
        <h2 class="text-h6 me-4">
          {{ store.currentConversation?.title || t('ai.untitled') }}
        </h2>
        <v-spacer />
        <v-select
          :model-value="effectiveTone"
          :items="toneOptions"
          :item-title="(o) => t(o.labelKey)"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          :label="t('ai.tone_label')"
          style="max-width: 220px;"
          class="me-2"
          @update:model-value="(v) => (overrideTone = v as AITone)"
        />
        <v-select
          :model-value="effectiveComplexity"
          :items="complexityOptions"
          :item-title="(o) => t(o.labelKey)"
          item-value="value"
          density="compact"
          variant="outlined"
          hide-details
          :label="t('ai.complexity_label')"
          style="max-width: 220px;"
          @update:model-value="(v) => (overrideComplexity = v as AIComplexity)"
        />
      </div>

      <!-- Лента сообщений -->
      <div
        ref="messagesContainer"
        class="flex-grow-1 overflow-y-auto pa-3"
        style="min-height: 0;"
      >
        <div v-if="!store.currentConversation" class="text-center text-disabled pt-6">
          {{ t('ai.empty_state') }}
        </div>
        <div v-else>
          <v-card
            v-for="m in store.messages"
            :key="m.id"
            class="mb-2 pa-3"
            :variant="m.role === 'user' ? 'tonal' : 'elevated'"
            :color="m.role === 'user' ? 'blue-lighten-5' : undefined"
            :class="{ 'safety-event': m.safety_event_type }"
          >
            <div class="text-caption text-disabled mb-1">
              {{ m.role === 'user' ? t('ai.role_user') : t('ai.role_assistant') }}
              <span v-if="m.tokens_used"> · {{ m.tokens_used }} {{ t('ai.tokens') }}</span>
              <span v-if="m.attached_data">
                · {{ t('ai.message_attached') }}
              </span>
            </div>
            <div class="message-content" style="white-space: pre-wrap;">{{ m.content }}</div>
          </v-card>
          <v-card v-if="store.isWaitingForResponse" class="mb-2 pa-3" variant="outlined">
            <v-progress-circular indeterminate size="20" class="me-2" />
            {{ t('ai.thinking') }}
          </v-card>
        </div>
      </div>

      <!-- Прикреплённые данные -->
      <div v-if="attached" class="px-3 pb-1">
        <v-chip closable color="primary" @click:close="attached = null">
          {{ t('ai.attached_prefix') }}: {{ attachedChip }}
        </v-chip>
      </div>

      <!-- Ошибки -->
      <v-alert
        v-if="errorMessage"
        type="error"
        density="compact"
        class="mx-3 mb-2"
        closable
        @click:close="errorMessage = null"
      >
        {{ errorMessage }}
      </v-alert>

      <!-- Поле ввода -->
      <div class="pa-3 d-flex align-end border-t">
        <v-btn
          variant="text"
          prepend-icon="mdi-paperclip"
          class="me-2"
          @click="attachDialog = true"
        >
          {{ t('ai.attach_button') }}
        </v-btn>
        <v-textarea
          v-model="messageText"
          :placeholder="t('ai.input_placeholder')"
          rows="2"
          auto-grow
          max-rows="6"
          variant="outlined"
          density="comfortable"
          hide-details
          @keydown.enter.exact.prevent="send"
        />
        <v-btn
          color="primary"
          class="ms-2"
          :disabled="!messageText.trim() || store.isWaitingForResponse"
          @click="send"
        >
          {{ t('ai.send') }}
        </v-btn>
      </div>
    </v-main>

    <AttachDataDialog
      v-model="attachDialog"
      :initial="attached"
      @attached="(d) => (attached = d)"
    />
  </v-container>
</template>

<style scoped>
.border-b {
  border-bottom: 1px solid rgba(0, 0, 0, 0.12);
}
.border-t {
  border-top: 1px solid rgba(0, 0, 0, 0.12);
}
.safety-event {
  border: 1px solid rgba(244, 67, 54, 0.5) !important;
}
.message-content {
  word-break: break-word;
}
</style>
