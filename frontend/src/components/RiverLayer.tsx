import { GeoJSON } from 'react-leaflet'

interface Props {
  geojson: object
}

export default function RiverLayer({ geojson }: Props) {
  return (
    <GeoJSON
      key={JSON.stringify(geojson).slice(0, 40)}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data={geojson as any}
      style={{
        color: '#dc2626',
        weight: 3,
        opacity: 0.85,
      }}
    />
  )
}
