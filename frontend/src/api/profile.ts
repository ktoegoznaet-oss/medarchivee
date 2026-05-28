import apiClient from './client'

export type Gender = 'male' | 'female' | 'not_specified'
export type AllergySeverity = 'mild' | 'moderate' | 'severe' | 'life_threatening'

export interface PatientProfile {
  id: number
  user_id: number
  first_name: string
  last_name: string
  middle_name: string | null
  birth_date: string
  gender: Gender
  blood_type: string | null
  height_cm: number | null
  weight_kg: number | null
  emergency_contact: string | null
  insurance_info: string | null
  city: string | null
  timezone: string
  updated_at: string
}

export interface PatientProfilePayload {
  first_name: string
  last_name: string
  middle_name?: string | null
  birth_date: string
  gender: Gender
  blood_type?: string | null
  height_cm?: number | null
  weight_kg?: number | null
  emergency_contact?: string | null
  insurance_info?: string | null
  city?: string | null
  timezone: string
}

export interface WeightRecord {
  id: number
  user_id: number
  weight_kg: number
  note: string | null
  recorded_at: string
}

export interface ChronicCondition {
  id: number
  user_id: number
  name: string
  icd10_code: string | null
  diagnosed_at: string | null
  note: string | null
  is_active: boolean
  created_at: string
}

export interface ChronicConditionPayload {
  name: string
  icd10_code?: string | null
  diagnosed_at?: string | null
  note?: string | null
  is_active?: boolean
}

export interface Allergy {
  id: number
  user_id: number
  allergen: string
  reaction: string | null
  note: string | null
  severity: AllergySeverity
  created_at: string
}

export interface AllergyPayload {
  allergen: string
  reaction?: string | null
  note?: string | null
  severity?: AllergySeverity
}

export interface FamilyHistoryRecord {
  id: number
  user_id: number
  relation: string
  condition: string
  note: string | null
  created_at: string
}

export interface ICD10Entry {
  code: string
  name: string
}

export const profileApi = {
  get() {
    return apiClient.get<PatientProfile>('/v1/profile')
  },
  create(payload: PatientProfilePayload) {
    return apiClient.post<PatientProfile>('/v1/profile', payload)
  },
  update(payload: Partial<PatientProfilePayload>) {
    return apiClient.patch<PatientProfile>('/v1/profile', payload)
  },
  listWeightHistory() {
    return apiClient.get<WeightRecord[]>('/v1/profile/weight-history')
  },
  addWeightRecord(weight_kg: number, note?: string) {
    return apiClient.post<WeightRecord>('/v1/profile/weight-history', {
      weight_kg,
      note: note ?? null,
    })
  },
  listChronic() {
    return apiClient.get<ChronicCondition[]>('/v1/profile/chronic-conditions')
  },
  createChronic(payload: ChronicConditionPayload) {
    return apiClient.post<ChronicCondition>('/v1/profile/chronic-conditions', payload)
  },
  updateChronic(id: number, payload: Partial<ChronicConditionPayload>) {
    return apiClient.patch<ChronicCondition>(`/v1/profile/chronic-conditions/${id}`, payload)
  },
  deleteChronic(id: number) {
    return apiClient.delete<void>(`/v1/profile/chronic-conditions/${id}`)
  },
  listAllergies() {
    return apiClient.get<Allergy[]>('/v1/profile/allergies')
  },
  createAllergy(payload: AllergyPayload) {
    return apiClient.post<Allergy>('/v1/profile/allergies', payload)
  },
  deleteAllergy(id: number) {
    return apiClient.delete<void>(`/v1/profile/allergies/${id}`)
  },
  searchIcd10(query: string) {
    return apiClient.get<ICD10Entry[]>('/v1/dictionaries/icd10', {
      params: { search: query, limit: 20 },
    })
  },
}
