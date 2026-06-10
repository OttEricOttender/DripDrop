const en: Record<string, string> = {
  appTitle: 'HydroCalc',
  appSubtitle: 'Karl Hommik design drainage',

  clickMapHint: 'Click on the map to select a point',

  coordInput: 'Coordinate input',
  tabLest97: 'L-EST97',
  tabWgs84: 'WGS84',
  eastingLabel: 'X (easting, m)',
  northingLabel: 'Y (northing, m)',
  latLabel: 'Latitude',
  lonLabel: 'Longitude',

  probLabel: 'Exceedance probability p (%)',

  calcButton: 'Calculate',
  clearButton: 'Clear',

  riverSection: 'River',
  catchmentSection: 'Catchment',
  landcoverSection: 'Land cover',
  resultsSection: 'Results',
  datasetsSection: 'Data sources',
  warningsSection: 'Warnings',

  riverName: 'Name',
  riverCode: 'KKR code',
  riverType: 'Type',
  riverLength: 'Length',
  riverIsMain: 'Main river',
  riverIsTributary: 'Tributary',

  catchmentArea: 'Area',
  catchmentCode: 'Catchment code',
  snapDistance: 'Distance to river',

  A_ms: 'Low bogs & bog forest (A_ms)',
  A_r: 'Raised bogs (A_r)',
  A_km: 'Drained low bogs (A_km)',
  B: 'Forest & shrub (B)',
  C: 'Bare mineral land (C)',
  maaparandus: 'Land improvement',
  a_wet_mineral_plus_akm: 'Parameter a',
  other: 'Other',

  Q_kev_max: 'Spring peak flow Q_kev',
  Q_veg_max: 'Autumn peak flow Q_veg',
  q_bar: 'Drainage norm q̄',
  delta_q: 'Correction Δq',
  k95: 'Coefficient k₉₅',
  r_s: 'Parameter r_s',
  r: 'Parameter r',
  q_kev_max_mod: 'Spring modulus',
  q_veg_max_mod: 'Autumn modulus',
  formulaRevision: 'Formula version',
  areaFloored: 'Area replaced with 100 km² (formula requirement)',

  unitKm2: 'km²',
  unitM3s: 'm³/s',
  unitM: 'm',
  unitLsKm2: 'l/(s·km²)',
  unitPct: '%',

  downloadPdf: 'Download PDF',
  downloadPdfLoading: 'Generating PDF…',
  downloadPdfError: 'PDF generation failed.',

  loading: 'Calculating…',
  errorGeneric: 'Error running analysis.',
}

export default en
