<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { adminApi } from '@/api/admin'
import type { RegistrationMode } from '@/api/auth'

const { t } = useI18n()

const mode = ref<RegistrationMode | null>(null)
const aiLimit = ref<number>(50)
const quotaMb = ref<number>(500)
const loading = ref(true)
const saving = ref(false)
const success = ref<string | null>(null)

onMounted(async () => {
  try {
    const [modeResp, limitsResp] = await Promise.all([
      adminApi.getRegistrationMode(),
      adminApi.getLimits(),
    ])
    mode.value = modeResp.data.mode
    aiLimit.value = limitsResp.data.ai_daily_limit
    quotaMb.value = Math.round(limitsResp.data.user_quota_bytes / 1024 / 1024)
  } finally {
    loading.value = false
  }
})

async function save(newMode: RegistrationMode): Promise<void> {
  saving.value = true
  success.value = null
  try {
    const resp = await adminApi.setRegistrationMode(newMode)
    mode.value = resp.data.mode
    success.value = t('admin.settings.saved')
  } finally {
    saving.value = false
  }
}

async function saveLimits(): Promise<void> {
  saving.value = true
  success.value = null
  try {
    const resp = await adminApi.setLimits({
      ai_daily_limit: aiLimit.value,
      user_quota_bytes: quotaMb.value * 1024 * 1024,
    })
    aiLimit.value = resp.data.ai_daily_limit
    quotaMb.value = Math.round(resp.data.user_quota_bytes / 1024 / 1024)
    success.value = t('admin.settings.saved')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-card-text>
    <v-progress-circular v-if="loading" indeterminate color="primary" />
    <div v-else>
      <h3 class="text-h6 mb-2">{{ t('admin.settings.registration_mode') }}</h3>
      <p class="text-caption mb-4">{{ t('admin.settings.registration_mode_hint') }}</p>

      <v-alert v-if="success" type="success" closable class="mb-4" @click:close="success = null">
        {{ success }}
      </v-alert>

      <v-radio-group :model-value="mode" :disabled="saving" @update:model-value="(v) => save(v as RegistrationMode)">
        <v-radio value="open">
          <template #label>
            <div>
              <div class="font-weight-medium">{{ t('admin.settings.mode_open') }}</div>
              <div class="text-caption text-disabled">{{ t('admin.settings.mode_open_hint') }}</div>
            </div>
          </template>
        </v-radio>
        <v-radio value="invite_only">
          <template #label>
            <div>
              <div class="font-weight-medium">{{ t('admin.settings.mode_invite_only') }}</div>
              <div class="text-caption text-disabled">{{ t('admin.settings.mode_invite_only_hint') }}</div>
            </div>
          </template>
        </v-radio>
        <v-radio value="closed">
          <template #label>
            <div>
              <div class="font-weight-medium">{{ t('admin.settings.mode_closed') }}</div>
              <div class="text-caption text-disabled">{{ t('admin.settings.mode_closed_hint') }}</div>
            </div>
          </template>
        </v-radio>
      </v-radio-group>

      <v-divider class="my-6" />

      <h3 class="text-h6 mb-2">{{ t('admin.settings.limits') }}</h3>
      <p class="text-caption mb-4">{{ t('admin.settings.limits_hint') }}</p>

      <v-text-field
        v-model.number="aiLimit"
        :label="t('admin.settings.ai_daily_limit')"
        type="number"
        min="0"
        density="compact"
      />
      <v-text-field
        v-model.number="quotaMb"
        :label="t('admin.settings.user_quota_mb')"
        type="number"
        min="0"
        density="compact"
      />
      <v-btn color="primary" :loading="saving" @click="saveLimits">
        {{ t('common.save') }}
      </v-btn>
    </div>
  </v-card-text>
</template>
