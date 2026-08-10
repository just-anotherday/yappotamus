import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'destructive'
export type ButtonTone = 'emerald' | 'amber' | 'orange'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: ButtonVariant
  tone?: ButtonTone
}

const primaryToneClasses: Record<ButtonTone, string> = {
  emerald: 'bg-emerald-700 text-white hover:bg-emerald-800 active:bg-emerald-900 disabled:bg-emerald-200 disabled:text-emerald-950 dark:disabled:bg-emerald-950 dark:disabled:text-emerald-100',
  amber: 'bg-amber-700 text-white hover:bg-amber-800 active:bg-amber-900 disabled:bg-amber-200 disabled:text-amber-950 dark:disabled:bg-amber-950 dark:disabled:text-amber-100',
  orange: 'bg-orange-700 text-white hover:bg-orange-800 active:bg-orange-900 disabled:bg-orange-200 disabled:text-orange-950 dark:disabled:bg-orange-950 dark:disabled:text-orange-100',
}

const secondaryToneClasses: Record<ButtonTone, string> = {
  emerald: 'border-stone-300 text-stone-700 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-800 dark:border-stone-700 dark:text-stone-200 dark:hover:border-emerald-800 dark:hover:bg-emerald-950/40 dark:hover:text-emerald-200',
  amber: 'border-stone-300 text-stone-700 hover:border-amber-300 hover:bg-amber-50 hover:text-amber-900 dark:border-stone-700 dark:text-stone-200 dark:hover:border-amber-800 dark:hover:bg-amber-950/40 dark:hover:text-amber-200',
  orange: 'border-stone-300 text-stone-700 hover:border-orange-300 hover:bg-orange-50 hover:text-orange-900 dark:border-stone-700 dark:text-stone-200 dark:hover:border-orange-800 dark:hover:bg-orange-950/40 dark:hover:text-orange-200',
}

const tertiaryToneClasses: Record<ButtonTone, string> = {
  emerald: 'text-emerald-800 hover:bg-emerald-50 hover:text-emerald-950 dark:text-emerald-300 dark:hover:bg-emerald-950/40 dark:hover:text-emerald-100',
  amber: 'text-amber-800 hover:bg-amber-50 hover:text-amber-950 dark:text-amber-300 dark:hover:bg-amber-950/40 dark:hover:text-amber-100',
  orange: 'text-orange-800 hover:bg-orange-50 hover:text-orange-950 dark:text-orange-300 dark:hover:bg-orange-950/40 dark:hover:text-orange-100',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  children,
  className = '',
  disabled,
  tone = 'emerald',
  type = 'button',
  variant = 'secondary',
  ...props
}: ButtonProps, ref) {
  const variantClasses = variant === 'primary'
    ? primaryToneClasses[tone]
    : variant === 'secondary'
      ? `border ${secondaryToneClasses[tone]}`
      : variant === 'tertiary'
        ? tertiaryToneClasses[tone]
        : 'text-red-700 hover:bg-red-50 hover:text-red-800 dark:text-red-300 dark:hover:bg-red-950/40 dark:hover:text-red-100'
  const disabledClasses = variant === 'primary'
    ? ''
    : 'disabled:border-stone-200 disabled:bg-stone-100 disabled:text-stone-500 dark:disabled:border-stone-800 dark:disabled:bg-stone-800 dark:disabled:text-stone-300'

  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-emerald-400 dark:focus-visible:ring-offset-stone-900 disabled:cursor-not-allowed ${disabledClasses} ${variantClasses} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
})
