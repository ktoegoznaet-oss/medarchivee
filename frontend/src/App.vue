<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'
import { useAnalysesStore } from '@/stores/analyses'
import { useAIStore } from '@/stores/ai'
import { useTelegramStore } from '@/stores/telegram'
import AppNavigation from '@/components/AppNavigation.vue'
import FeedbackButton from '@/components/FeedbackButton.vue'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()
const profileStore = useProfileStore()
const analysesStore = useAnalysesStore()
const aiStore = useAIStore()
const telegramStore = useTelegramStore()

const drawerOpen = ref(true)

function resetAllStores(): void {
  // Сбрасываем все per-user stores при logout — иначе при смене аккаунта
  // в той же вкладке на пару секунд видны данные предыдущего пользователя.
  profileStore.reset()
  analysesStore.reset()
  aiStore.reset()
  telegramStore.reset()
}

auth.registerAuthLostHandler(() => {
  resetAllStores()
  router.push({ name: 'login' })
})

onMounted(async () => {
  await auth.tryRestoreSession()
})

async function handleLogout(): Promise<void> {
  await auth.logout()
  resetAllStores()
  router.push({ name: 'login' })
}
</script>

<template>
  <v-app>
    <template v-if="auth.isAuthenticated">
      <v-app-bar color="primary" density="comfortable">
        <v-app-bar-nav-icon @click="drawerOpen = !drawerOpen" />
        <v-app-bar-title>{{ t('app.title') }}</v-app-bar-title>
        <template #append>
          <v-menu>
            <template #activator="{ props }">
              <v-btn v-bind="props" variant="text">
                <v-icon icon="mdi-account-circle" start />
                {{ auth.user?.username ?? auth.user?.email }}
              </v-btn>
            </template>
            <v-list>
              <v-list-item @click="handleLogout">
                <template #prepend>
                  <v-icon icon="mdi-logout" />
                </template>
                <v-list-item-title>{{ t('app.logout') }}</v-list-item-title>
              </v-list-item>
            </v-list>
          </v-menu>
        </template>
      </v-app-bar>

      <AppNavigation v-model="drawerOpen" />
    </template>

    <v-main>
      <router-view />
    </v-main>

    <FeedbackButton v-if="auth.isAuthenticated" />
  </v-app>
</template>
