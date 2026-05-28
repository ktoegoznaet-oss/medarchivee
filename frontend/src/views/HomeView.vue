<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useProfileStore } from '@/stores/profile'
import { useAnalysesStore } from '@/stores/analyses'

const { t } = useI18n()
const router = useRouter()
const profileStore = useProfileStore()
const analysesStore = useAnalysesStore()

onMounted(async () => {
  if (!profileStore.profileChecked) {
    await profileStore.fetchProfile()
  }
  await analysesStore.fetchList()
})

const greeting = computed(() => {
  const name = profileStore.profile?.first_name
  return name
    ? t('home.greeting_named', { name })
    : t('home.greeting_anonymous')
})

const lastAnalyses = computed(() => analysesStore.records.slice(0, 3))

const upcomingModules: { titleKey: string; subtitleKey: string; icon: string }[] = []
</script>

<template>
  <v-container fluid>
    <h1 class="text-h4 mb-4">{{ greeting }}</h1>

    <v-row>
      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <v-card-title>{{ t('home.profile_card_title') }}</v-card-title>
          <v-card-text v-if="profileStore.profile">
            <p>
              <strong>{{ profileStore.profile.last_name }}
                {{ profileStore.profile.first_name }}</strong>
            </p>
            <p>{{ t('profile.birth_date') }}: {{ profileStore.profile.birth_date }}</p>
            <p v-if="profileStore.profile.city">
              {{ t('profile.city') }}: {{ profileStore.profile.city }}
            </p>
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" variant="text" @click="router.push({ name: 'profile' })">
              {{ t('home.open_profile') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card class="pa-4">
          <v-card-title class="d-flex align-center">
            <span>{{ t('home.analyses_card_title') }}</span>
            <v-spacer />
            <v-btn color="primary" variant="text" @click="router.push({ name: 'analyses' })">
              {{ t('home.all_analyses') }}
            </v-btn>
          </v-card-title>
          <v-list v-if="lastAnalyses.length > 0" density="compact">
            <v-list-item
              v-for="r in lastAnalyses"
              :key="r.id"
              :title="r.analysis_date"
              :subtitle="r.lab_name ?? t('analyses.list.no_lab')"
              @click="router.push({ name: 'analyses-detail', params: { id: r.id } })"
            >
              <template #append>
                <v-chip
                  :color="r.abnormal_count > 0 ? 'red' : undefined"
                  variant="tonal"
                  size="small"
                >
                  {{ t('analyses.list.summary', { total: r.values_count, abnormal: r.abnormal_count }) }}
                </v-chip>
              </template>
            </v-list-item>
          </v-list>
          <p v-else class="text-disabled mt-2">{{ t('home.analyses_empty') }}</p>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card class="pa-4">
          <v-card-title>
            <v-icon icon="mdi-robot-happy" start />
            {{ t('home.modules.ivan') }}
          </v-card-title>
          <v-card-text>{{ t('home.ivan_hint') }}</v-card-text>
          <v-card-actions>
            <v-btn color="primary" variant="text" @click="router.push({ name: 'ai-chat' })">
              {{ t('home.open_chat') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card class="pa-4">
          <v-card-title>
            <v-icon icon="mdi-telegram" start />
            {{ t('home.modules.telegram') }}
          </v-card-title>
          <v-card-text>{{ t('home.telegram_hint') }}</v-card-text>
          <v-card-actions>
            <v-btn color="primary" variant="text" @click="router.push({ name: 'settings-telegram' })">
              {{ t('home.open_telegram') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col v-for="m in upcomingModules" :key="m.titleKey" cols="12" md="6" lg="4">
        <v-tooltip :text="t('home.module_disabled')" location="top">
          <template #activator="{ props }">
            <v-card v-bind="props" class="pa-4" variant="outlined" disabled>
              <v-card-title>
                <v-icon :icon="m.icon" start />
                {{ t(m.titleKey) }}
              </v-card-title>
              <v-card-subtitle>{{ t(m.subtitleKey) }}</v-card-subtitle>
            </v-card>
          </template>
        </v-tooltip>
      </v-col>
    </v-row>
  </v-container>
</template>
