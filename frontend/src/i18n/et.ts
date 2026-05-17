const et: Record<string, string> = {
  // Header
  appTitle: 'HydroCalc',
  appSubtitle: 'Karl Hommik äravoolunorm',

  // Map
  clickMapHint: 'Klõpsa kaardil, et valida punkt',

  // CoordInput
  coordInput: 'Koordinaatide sisestus',
  tabLest97: 'L-EST97',
  tabWgs84: 'WGS84',
  eastingLabel: 'X (idapikkus, m)',
  northingLabel: 'Y (põhjalaius, m)',
  latLabel: 'Laiuskraad',
  lonLabel: 'Pikkuskraad',

  // Probability
  probLabel: 'Ületõusutõenäosus p (%)',

  // Buttons
  calcButton: 'Arvuta',
  clearButton: 'Tühjenda',

  // Result sections
  riverSection: 'Vooluveekogu',
  catchmentSection: 'Valgala',
  landcoverSection: 'Maakasutus',
  resultsSection: 'Arvutustulemused',
  datasetsSection: 'Andmeallikad',
  warningsSection: 'Hoiatused',

  // River
  riverName: 'Nimi',
  riverCode: 'KKR kood',
  riverType: 'Tüüp',
  riverLength: 'Pikkus',
  riverIsMain: 'Peajõgi',
  riverIsTributary: 'Lisajõgi',

  // Catchment
  catchmentArea: 'Pindala',
  catchmentCode: 'Valgala kood',
  snapDistance: 'Kaugus jõest',

  // Land cover
  A_ms: 'Madalsood ja soometsad (A_ms)',
  A_r: 'Rabad (A_r)',
  A_km: 'Kuivendatud madalsood (A_km)',
  B: 'Mets ja võsa (B)',
  C: 'Lage mineraalmaa (C)',
  maaparandus: 'Maaparandus',
  a_wet_mineral_plus_akm: 'Parameeter a',

  // Hommik
  Q_kev_max: 'Kevadine tippvooluhulk Q_kev',
  Q_veg_max: 'Sügisene tippvooluhulk Q_veg',
  q_bar: 'Äravoolunorm q̄',
  delta_q: 'Parand Δq',
  k95: 'Koefitsient k₉₅',
  r_s: 'Parameeter r_s',
  r: 'Parameeter r',
  q_kev_max_mod: 'Kevadine moodul',
  q_veg_max_mod: 'Sügisene moodul',
  formulaRevision: 'Valemiversioon',
  areaFloored: 'Pindala asendati 100 km²-ga (valemite nõue)',

  // Units
  unitKm2: 'km²',
  unitM3s: 'm³/s',
  unitM: 'm',
  unitLsKm2: 'l/(s·km²)',
  unitPct: '%',

  // Status / errors
  loading: 'Arvutan…',
  errorGeneric: 'Viga analüüsi käivitamisel.',
}

export default et
