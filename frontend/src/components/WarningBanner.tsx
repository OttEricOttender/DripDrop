interface Props {
  message: string
  isPlaceholder?: boolean
}

export default function WarningBanner({ message, isPlaceholder = false }: Props) {
  const base = isPlaceholder
    ? 'bg-amber-50 border-amber-400 text-amber-900'
    : 'bg-yellow-50 border-yellow-400 text-yellow-900'
  return (
    <div className={`border-l-4 px-3 py-2 rounded text-sm ${base}`}>
      <span className="font-semibold">⚠ </span>
      {message}
    </div>
  )
}
