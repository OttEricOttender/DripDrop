import React from 'react'
import { cn } from '../../lib/utils'

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'outline' | 'secondary' | 'teal'
}

export function Badge({ variant = 'default', className, children, ...props }: BadgeProps) {
  const variants = {
    default: 'bg-blue-100 text-blue-800',
    outline: 'border border-slate-300 text-slate-600',
    secondary: 'bg-slate-100 text-slate-700',
    teal: 'bg-teal-100 text-teal-800',
  }
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        variants[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}
