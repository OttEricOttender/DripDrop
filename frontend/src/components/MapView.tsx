import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, CircleMarker, Tooltip, useMapEvents, useMap, LayersControl } from 'react-leaflet'
import L from 'leaflet'
import type { GeoJsonObject } from 'geojson'
import CatchmentLayer from './CatchmentLayer'
import RiverLayer from './RiverLayer'
import type { AnalysisResult } from '../api/types'
import { useT } from '../i18n'

// Maa-amet tile layers (TMS — inverted Y axis requires tms: true)
const MAAAMET_AERIAL = 'https://tiles.maaamet.ee/tm/tms/1.0.0/foto@GMC/{z}/{x}/{y}.png'
const MAAAMET_MAP    = 'https://tiles.maaamet.ee/tm/tms/1.0.0/kaart@GMC/{z}/{x}/{y}.png'
const MAAAMET_ATTR   = '&copy; <a href="https://maaamet.ee" target="_blank">Maa-amet</a>'

function ClickHandler({ onMapClick }: { onMapClick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: e => onMapClick(e.latlng.lat, e.latlng.lng) })
  return null
}

function FitCatchment({ result }: { result: AnalysisResult | null }) {
  const map = useMap()
  useEffect(() => {
    if (!result?.catchment_geojson) return
    try {
      const bounds = L.geoJSON(result.catchment_geojson as GeoJsonObject).getBounds()
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40] })
    } catch { /* leave map at current view */ }
  }, [result, map])
  return null
}

interface Props {
  onMapClick: (lat: number, lon: number) => void
  clickedPoint: { lat: number; lon: number } | null
  result: AnalysisResult | null
}

export default function MapView({ onMapClick, clickedPoint, result }: Props) {
  const { t } = useT()
  return (
    <MapContainer
      center={[58.8, 25.5]}
      zoom={7}
      style={{ height: '100%', width: '100%' }}
    >
      {/*
        Maa-amet tiles use TMS (y-inverted). The `tms` prop is valid in Leaflet
        but not in the react-leaflet typings, hence the cast.
        kaart@GMC includes city/village/road labels; foto@GMC is aerial only.
      */}
      <LayersControl position="topright">
        <LayersControl.BaseLayer name="Kaart (kohanimedega)">
          <TileLayer
            {...({ tms: true } as object)}
            url={MAAAMET_MAP}
            attribution={MAAAMET_ATTR}
            maxZoom={18}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer checked name="Ortofoto">
          <TileLayer
            {...({ tms: true } as object)}
            url={MAAAMET_AERIAL}
            attribution={MAAAMET_ATTR}
            maxZoom={18}
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <ClickHandler onMapClick={onMapClick} />
      <FitCatchment result={result} />

      {result?.river_geojson && (
        <RiverLayer geojson={result.river_geojson} />
      )}
      {result?.catchment_geojson && (
        <CatchmentLayer geojson={result.catchment_geojson} />
      )}

      {/* Blue pin — original click location */}
      {clickedPoint && (
        <Marker position={[clickedPoint.lat, clickedPoint.lon]}>
          <Tooltip>{t('clickedHere')}</Tooltip>
        </Marker>
      )}

      {/* Red circle — snapped stream point, shown once result is ready */}
      {result?.snapped_point_wgs84 && (
        <CircleMarker
          center={[result.snapped_point_wgs84.lat, result.snapped_point_wgs84.lon]}
          radius={8}
          pathOptions={{ color: '#991b1b', fillColor: '#ef4444', fillOpacity: 0.9, weight: 2 }}
        >
          <Tooltip direction="top" offset={[0, -12]}>{t('snappedToRiver')}</Tooltip>
          <Popup>
            <strong>{result.river.name}</strong><br />
            {result.catchment.area_km2.toFixed(1)} km²
          </Popup>
        </CircleMarker>
      )}
    </MapContainer>
  )
}
