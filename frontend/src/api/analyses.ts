import apiClient from './client'

export type AbnormalType = 'low' | 'high' | 'normal' | 'unknown'

export interface AnalysisValueInput {
  parameter_code: string | null
  parameter_name: string
  value: string
  unit: string
  reference_min: string | null
  reference_max: string | null
}

export interface AnalysisValue {
  id: number
  record_id: number
  user_id: number
  parameter_code: string | null
  parameter_name: string
  value: string
  unit: string
  reference_min: string | null
  reference_max: string | null
  is_abnormal: boolean
  abnormal_type: AbnormalType
}

export interface AnalysisRecordSummary {
  id: number
  user_id: number
  analysis_date: string
  lab_name: string | null
  values_count: number
  abnormal_count: number
}

export interface AnalysisRecordFull {
  id: number
  user_id: number
  analysis_date: string
  lab_name: string | null
  doctor_referral: string | null
  notes: string | null
  created_at: string
  values: AnalysisValue[]
}

export interface AnalysisRecordCreate {
  analysis_date: string
  lab_name: string | null
  doctor_referral: string | null
  notes: string | null
  values: AnalysisValueInput[]
}

export interface AnalysisHistoryPoint {
  analysis_date: string
  value: string
  value_numeric: number | null
  unit: string
  reference_min: string | null
  reference_max: string | null
  is_abnormal: boolean
  abnormal_type: AbnormalType
}

export interface AnalysisHistory {
  parameter_code: string
  parameter_name: string | null
  unit: string | null
  points: AnalysisHistoryPoint[]
}

export interface AnalysisParameterSummary {
  code: string
  name_ru: string
  unit: string
  category: string
}

export interface AnalysisParameterDetail extends AnalysisParameterSummary {
  name_en: string
  alternative_units: string[]
  description: string | null
  synonyms: string[]
  applicable_norm: {
    min: number | null
    max: number | null
    gender: string
    age_from: number
    age_to: number
  } | null
}

export interface AnalysesFilters {
  date_from?: string
  date_to?: string
  only_abnormal?: boolean
}

export const analysesApi = {
  list(filters: AnalysesFilters = {}) {
    return apiClient.get<AnalysisRecordSummary[]>('/v1/analyses', { params: filters })
  },
  get(id: number) {
    return apiClient.get<AnalysisRecordFull>(`/v1/analyses/${id}`)
  },
  create(payload: AnalysisRecordCreate) {
    return apiClient.post<AnalysisRecordFull>('/v1/analyses', payload)
  },
  update(id: number, payload: Partial<Pick<AnalysisRecordCreate, 'lab_name' | 'doctor_referral' | 'notes' | 'analysis_date'>>) {
    return apiClient.patch<AnalysisRecordFull>(`/v1/analyses/${id}`, payload)
  },
  remove(id: number) {
    return apiClient.delete<void>(`/v1/analyses/${id}`)
  },
  updateValue(valueId: number, payload: Partial<AnalysisValueInput>) {
    return apiClient.patch<AnalysisValue>(`/v1/analyses/values/${valueId}`, payload)
  },
  history(parameterCode: string, dateFrom?: string, dateTo?: string) {
    return apiClient.get<AnalysisHistory>(
      `/v1/analyses/parameters/${parameterCode}/history`,
      { params: { date_from: dateFrom, date_to: dateTo } },
    )
  },
  searchParameters(query: string) {
    return apiClient.get<AnalysisParameterSummary[]>(
      '/v1/dictionaries/analysis-parameters',
      { params: { search: query, limit: 20 } },
    )
  },
  parameterDetail(code: string, gender: string, age: number) {
    return apiClient.get<AnalysisParameterDetail>(
      `/v1/dictionaries/analysis-parameters/${code}`,
      { params: { gender, age } },
    )
  },
}
