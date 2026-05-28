<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const tabs = [
  { name: 'admin-dashboard', titleKey: 'admin.tabs.dashboard', icon: 'mdi-view-dashboard' },
  { name: 'admin-users', titleKey: 'admin.tabs.users', icon: 'mdi-account-multiple' },
  { name: 'admin-invites', titleKey: 'admin.tabs.invites', icon: 'mdi-ticket-account' },
  { name: 'admin-tickets', titleKey: 'admin.tabs.tickets', icon: 'mdi-message-text' },
  { name: 'admin-settings', titleKey: 'admin.tabs.settings', icon: 'mdi-cog' },
]
</script>

<template>
  <v-container fluid>
    <v-card>
      <v-tabs
        :model-value="route.name?.toString()"
        color="primary"
        align-tabs="start"
        @update:model-value="(v) => router.push({ name: v as string })"
      >
        <v-tab
          v-for="tab in tabs"
          :key="tab.name"
          :value="tab.name"
          :prepend-icon="tab.icon"
        >
          {{ t(tab.titleKey) }}
        </v-tab>
      </v-tabs>
      <v-divider />
      <router-view />
    </v-card>
  </v-container>
</template>
