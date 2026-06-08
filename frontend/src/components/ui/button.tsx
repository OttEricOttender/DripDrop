import React from 'react'
import { cn } from '../../lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'default' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg' | 'full'
}

export function Button({
  variant = 'default',
  size = 'md',
  className,
  children,
  ...props
}: ButtonProps) {
  const variants = {
    default: 'bg-blue-700 text-white hover:bg-blue-800 disabled:bg-blue-300 disabled:cursor-not-allowed',
    outline: 'border border-blue-600 text-blue-700 hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed',
    ghost: 'text-slate-600 hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed',
  }
  const sizes = {
    sm: 'px-3 py-1 text-xs',
    md: 'px-4 py-2 text-sm',
    lg: 'px-5 py-2.5 text-base',
    full: 'w-full py-2.5 text-sm',
  }
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-semibold transition-colors',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}
