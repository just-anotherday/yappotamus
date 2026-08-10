import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Button, type ButtonTone, type ButtonVariant } from './Button'

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'children'> {
  ariaLabel: string
  children: ReactNode
  tone?: ButtonTone
  variant?: ButtonVariant
}

export function IconButton({
  ariaLabel,
  children,
  className = '',
  tone,
  variant = 'tertiary',
  ...props
}: IconButtonProps) {
  return (
    <Button
      aria-label={ariaLabel}
      title={props.title ?? ariaLabel}
      tone={tone}
      variant={variant}
      className={`size-10 min-h-10 shrink-0 !px-0 !py-0 ${className}`}
      {...props}
    >
      {children}
    </Button>
  )
}
