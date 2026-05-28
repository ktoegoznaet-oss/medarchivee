import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  profileApi,
  type Allergy,
  type AllergyPayload,
  type ChronicCondition,
  type ChronicConditionPayload,
  type FamilyHistoryRecord,
  type PatientProfile,
  type PatientProfilePayload,
  type WeightRecord,
} from '@/api/profile'

export const useProfileStore = defineStore('profile', () => {
  const profile = ref<PatientProfile | null>(null)
  const profileChecked = ref(false)
  const chronicConditions = ref<ChronicCondition[]>([])
  const allergies = ref<Allergy[]>([])
  const family = ref<FamilyHistoryRecord[]>([])
  const weightHistory = ref<WeightRecord[]>([])
  const loading = ref(false)

  async function fetchProfile(): Promise<PatientProfile | null> {
    loading.value = true
    try {
      const { data } = await profileApi.get()
      profile.value = data
      profileChecked.value = true
      return data
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 404) {
        profile.value = null
        profileChecked.value = true
        return null
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  async function createProfile(payload: PatientProfilePayload): Promise<PatientProfile> {
    const { data } = await profileApi.create(payload)
    profile.value = data
    return data
  }

  async function updateProfile(
    payload: Partial<PatientProfilePayload>,
  ): Promise<PatientProfile> {
    const { data } = await profileApi.update(payload)
    profile.value = data
    return data
  }

  async function fetchWeightHistory(): Promise<void> {
    const { data } = await profileApi.listWeightHistory()
    weightHistory.value = data
  }

  async function addWeightRecord(weight: number, note?: string): Promise<void> {
    await profileApi.addWeightRecord(weight, note)
    await Promise.all([fetchWeightHistory(), fetchProfile()])
  }

  async function fetchChronic(): Promise<void> {
    const { data } = await profileApi.listChronic()
    chronicConditions.value = data
  }

  async function addChronic(payload: ChronicConditionPayload): Promise<void> {
    await profileApi.createChronic(payload)
    await fetchChronic()
  }

  async function updateChronic(
    id: number,
    payload: Partial<ChronicConditionPayload>,
  ): Promise<void> {
    await profileApi.updateChronic(id, payload)
    await fetchChronic()
  }

  async function deleteChronic(id: number): Promise<void> {
    await profileApi.deleteChronic(id)
    await fetchChronic()
  }

  async function fetchAllergies(): Promise<void> {
    const { data } = await profileApi.listAllergies()
    allergies.value = data
  }

  async function addAllergy(payload: AllergyPayload): Promise<void> {
    await profileApi.createAllergy(payload)
    await fetchAllergies()
  }

  async function deleteAllergy(id: number): Promise<void> {
    await profileApi.deleteAllergy(id)
    await fetchAllergies()
  }

  function reset(): void {
    profile.value = null
    profileChecked.value = false
    chronicConditions.value = []
    allergies.value = []
    family.value = []
    weightHistory.value = []
  }

  return {
    profile,
    profileChecked,
    chronicConditions,
    allergies,
    family,
    weightHistory,
    loading,
    fetchProfile,
    createProfile,
    updateProfile,
    fetchWeightHistory,
    addWeightRecord,
    fetchChronic,
    addChronic,
    updateChronic,
    deleteChronic,
    fetchAllergies,
    addAllergy,
    deleteAllergy,
    reset,
  }
})
