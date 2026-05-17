import { GeoJSON } from 'react-leaflet'

interface Props {
  geojson: object
}

export default function CatchmentLayer({ geojson }: Props) {
  return (
    <GeoJSON
      key={JSON.stringify(geojson).slice(0, 40)}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data={geojson as any}
      style={{
        color: '#1d4ed8',
        weight: 2,
        fillColor: '#3b82f6',
        fillOpacity: 0.15,
      }}
    />
  )
}
