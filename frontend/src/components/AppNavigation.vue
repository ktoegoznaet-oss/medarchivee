<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

defineProps<{ modelValue: boolean }>()
defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

interface NavChild {
  icon: string
  titleKey: string
  to: { name: string }
}

interface NavItem {
  icon: string
  titleKey: string
  to?: { name: string }
  disabledHintKey?: string
  children?: NavChild[]
}

const items: NavItem[] = [
  { icon: 'mdi-home', titleKey: 'nav.home', to: { name: 'home' } },
  { icon: 'mdi-account', titleKey: 'nav.profile', to: { name: 'profile' } },
  { icon: 'mdi-flask', titleKey: 'nav.analyses', to: { name: 'analyses' } },
  { icon: 'mdi-robot-happy', titleKey: 'nav.ivan', to: { name: 'ai-chat' } },
  { icon: 'mdi-message-text', titleKey: 'tickets.nav', to: { name: 'tickets-list' } },
  {
    icon: 'mdi-cog',
    titleKey: 'nav.settings',
    children: [
      {
        icon: 'mdi-telegram',
        titleKey: 'nav.settings_telegram',
        to: { name: 'settings-telegram' },
      },
      {
        icon: 'mdi-shield-key',
        titleKey: 'account.nav',
        to: { name: 'account-settings' },
      },
    ],
  },
]

function go(item: NavItem): void {
  if (item.to) router.push(item.to)
}
</script>

<template>
  <v-navigation-drawer
    :model-value="modelValue"
    @update:model-value="(v) => $emit('update:modelValue', v)"
  >
    <v-list nav>
      <template v-for="item in items" :key="item.titleKey">
        <v-tooltip
          v-if="item.disabledHintKey"
          :text="t(item.disabledHintKey)"
          location="end"
        >
          <template #activator="{ props }">
            <v-list-item v-bind="props" :prepend-icon="item.icon" :title="t(item.titleKey)" disabled />
          </template>
        </v-tooltip>
        <v-list-group v-else-if="item.children" :value="item.titleKey">
          <template #activator="{ props }">
            <v-list-item
              v-bind="props"
              :prepend-icon="item.icon"
              :title="t(item.titleKey)"
            />
          </template>
          <v-list-item
            v-for="child in item.children"
            :key="child.titleKey"
            :prepend-icon="child.icon"
            :title="t(child.titleKey)"
            :active="route.name === child.to.name"
            @click="router.push(child.to)"
          />
        </v-list-group>
        <v-list-item
          v-else
          :prepend-icon="item.icon"
          :title="t(item.titleKey)"
          :active="item.to && route.name === item.to.name"
          @click="go(item)"
        />
      </template>

      <v-divider v-if="auth.isAdmin" class="my-2" />
      <v-list-item
        v-if="auth.isAdmin"
        prepend-icon="mdi-shield-account"
        :title="t('admin.nav')"
        :active="route.path.startsWith('/admin')"
        @click="router.push({ name: 'admin-dashboard' })"
      />
    </v-list>
  </v-navigation-drawer>
</template>
