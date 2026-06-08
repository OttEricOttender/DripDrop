import React from 'react'
import { cn } from '../../lib/utils'

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900',
        'placeholder:text-slate-400',
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
        'transition-shadow',
        className,
      )}
      {...props}
    />
  )
}
