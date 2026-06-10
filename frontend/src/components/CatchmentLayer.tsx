import { GeoJSON } from 'react-leaflet'
import type { GeoJsonObject } from 'geojson'

interface Props {
  geojson: GeoJsonObject
}

export default function CatchmentLayer({ geojson }: Props) {
  return (
    <GeoJSON
      key={JSON.stringify(geojson).slice(0, 40)}
      data={geojson}
      style={{
        color: '#1d4ed8',
        weight: 2,
        fillColor: '#3b82f6',
        fillOpacity: 0.15,
      }}
    />
  )
}
