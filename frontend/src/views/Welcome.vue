<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const auth = useAuthStore()

const healthStatus = ref<string>('—')
const healthError = ref<string | null>(null)

onMounted(async () => {
  try {
    const { data } = await apiClient.get<{ status: string; version: string }>('/health')
    healthStatus.value = `${data.status} (v${data.version})`
  } catch (err) {
    healthError.value = err instanceof Error ? err.message : String(err)
  }
})
</script>

<template>
  <v-container class="fill-height" fluid>
    <v-row align="center" justify="center">
      <v-col cols="12" md="8" lg="6">
        <v-card elevation="2" class="pa-6">
          <v-card-title class="text-h4">
            {{ t('welcome.title') }}
          </v-card-title>
          <v-card-subtitle class="text-subtitle-1">
            {{ t('welcome.subtitle', { name: auth.user?.username ?? '' }) }}
          </v-card-subtitle>
          <v-card-text>
            <p class="text-body-1 mb-2">{{ t('welcome.stage') }}</p>
            <p class="text-body-2">
              {{ t('welcome.healthLabel') }}:
              <strong>{{ healthStatus }}</strong>
            </p>
            <p v-if="healthError" class="text-error text-body-2">
              {{ t('welcome.healthError') }}: {{ healthError }}
            </p>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>
