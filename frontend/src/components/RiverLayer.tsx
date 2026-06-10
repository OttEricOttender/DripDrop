import { GeoJSON } from 'react-leaflet'
import type { GeoJsonObject } from 'geojson'

interface Props {
  geojson: GeoJsonObject
}

export default function RiverLayer({ geojson }: Props) {
  return (
    <GeoJSON
      key={JSON.stringify(geojson).slice(0, 40)}
      data={geojson}
      style={{
        color: '#dc2626',
        weight: 3,
        opacity: 0.85,
      }}
    />
  )
}
