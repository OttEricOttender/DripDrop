// TypeScript interfaces mirroring backend/models/schemas.py — keep in sync manually.

import type { GeoJsonObject } from 'geojson'

export interface CoordinateWGS84 {
  lat: number
  lon: number
}

export interface CoordinateLEST97 {
  x: number
  y: number
}

export interface AnalysisRequest {
  point_wgs84?: CoordinateWGS84
  point_lest97?: CoordinateLEST97
  p_percent?: number
}

export interface LandCoverBreakdown {
  A_ms: number
  A_r: number
  A_km: number
  B: number
  C: number
  maaparandus: number
  a_wet_mineral_plus_akm: number
}

export interface RiverInfo {
  code: string
  name: string
  river_type: string | null
  length_m: number | null
  is_main: boolean
}

export interface CatchmentInfo {
  code: string | null
  name: string | null
  area_km2: number
  dem_resolution_m: number
}

export interface HommikResult {
  q_bar_l_per_s_km2: number
  delta_q_l_per_s_km2: number
  k95: number
  r_s: number
  r: number
  q_veg_max_l_per_s_km2: number
  q_kev_max_l_per_s_km2: number
  Q_veg_max_m3_per_s: number
  Q_kev_max_m3_per_s: number
  formula_revision: string
  area_floored_to_100km2: boolean
  q_bar_k_source: 'raster' | 'placeholder'
}

export interface DatasetVersion {
  name: string
  source_url: string
  sha256: string
  retrieved_at: string
  crs: string
}

export interface AnalysisResult {
  run_id: string
  timestamp: string
  input_point_lest97: CoordinateLEST97
  snapped_point_lest97: CoordinateLEST97
  snap_distance_m: number
  river: RiverInfo
  catchment: CatchmentInfo
  landcover: LandCoverBreakdown
  hommik: HommikResult
  catchment_geojson: GeoJsonObject | null
  river_geojson: GeoJsonObject | null
  dataset_versions: DatasetVersion[]
  warnings: string[]
  q_bar_k_is_placeholder: boolean
}
