import { Alert } from './ui/alert'

interface Props {
  message: string
  isPlaceholder?: boolean
}

export default function WarningBanner({ message, isPlaceholder = false }: Props) {
  return (
    <Alert variant={isPlaceholder ? 'amber' : 'warning'}>
      <span className="font-semibold">⚠ </span>
      {message}
    </Alert>
  )
}
