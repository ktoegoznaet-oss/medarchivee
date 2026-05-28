<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAnalysesStore } from '@/stores/analyses'

const { t } = useI18n()
const router = useRouter()
const store = useAnalysesStore()

const filtersOpen = ref(false)
const dateFrom = ref('')
const dateTo = ref('')
const onlyAbnormal = ref(false)

async function reload(): Promise<void> {
  await store.fetchList({
    date_from: dateFrom.value || undefined,
    date_to: dateTo.value || undefined,
    only_abnormal: onlyAbnormal.value || undefined,
  })
}

onMounted(reload)
watch([dateFrom, dateTo, onlyAbnormal], reload)

function summaryColor(count: number): string | undefined {
  return count > 0 ? 'red' : undefined
}
</script>

<template>
  <v-container fluid>
    <div class="d-flex align-center mb-4">
      <h1 class="text-h4">{{ t('analyses.list.title') }}</h1>
      <v-spacer />
      <v-btn color="primary" prepend-icon="mdi-plus" @click="router.push({ name: 'analyses-create' })">
        {{ t('analyses.list.add') }}
      </v-btn>
    </div>

    <v-card class="mb-4">
      <v-card-actions>
        <v-btn variant="text" @click="filtersOpen = !filtersOpen">
          <v-icon icon="mdi-filter-variant" start />
          {{ t('analyses.list.filters') }}
        </v-btn>
      </v-card-actions>
      <v-expand-transition>
        <div v-if="filtersOpen" class="pa-4">
          <v-row dense>
            <v-col cols="12" md="4">
              <v-text-field v-model="dateFrom" :label="t('analyses.list.date_from')" type="date" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model="dateTo" :label="t('analyses.list.date_to')" type="date" />
            </v-col>
            <v-col cols="12" md="4" class="d-flex align-center">
              <v-checkbox
                v-model="onlyAbnormal"
                :label="t('analyses.list.only_abnormal')"
                density="compact"
              />
            </v-col>
          </v-row>
        </div>
      </v-expand-transition>
    </v-card>

    <v-list lines="two">
      <v-list-item
        v-for="r in store.records"
        :key="r.id"
        :title="r.analysis_date"
        :subtitle="r.lab_name ?? t('analyses.list.no_lab')"
        @click="router.push({ name: 'analyses-detail', params: { id: r.id } })"
      >
        <template #append>
          <v-chip :color="summaryColor(r.abnormal_count)" variant="tonal" size="small">
            {{ t('analyses.list.summary', { total: r.values_count, abnormal: r.abnormal_count }) }}
          </v-chip>
        </template>
      </v-list-item>
      <v-list-item v-if="store.records.length === 0 && !store.loading">
        <v-list-item-title class="text-disabled">
          {{ t('analyses.list.empty') }}
        </v-list-item-title>
      </v-list-item>
    </v-list>
  </v-container>
</template>
