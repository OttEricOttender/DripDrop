import React from 'react'
import { cn } from '../../lib/utils'

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'warning' | 'amber' | 'destructive' | 'info'
}

export function Alert({ variant = 'warning', className, children, ...props }: AlertProps) {
  const variants = {
    warning: 'border-l-4 border-yellow-400 bg-yellow-50 text-yellow-900',
    amber: 'border-l-4 border-amber-400 bg-amber-50 text-amber-900',
    destructive: 'border-l-4 border-red-400 bg-red-50 text-red-900',
    info: 'border-l-4 border-blue-400 bg-blue-50 text-blue-900',
  }
  return (
    <div
      className={cn('rounded-lg px-3 py-2.5 text-sm', variants[variant], className)}
      {...props}
    >
      {children}
    </div>
  )
}
