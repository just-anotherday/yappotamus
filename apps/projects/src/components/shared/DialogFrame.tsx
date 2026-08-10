import { useEffect, useRef, type KeyboardEvent, type ReactNode, type RefObject } from 'react'

interface DialogFrameProps {
  labelledBy: string
  pending?: boolean
  onClose: () => void
  initialFocusRef?: RefObject<HTMLElement | null>
  children: ReactNode
  className?: string
}

export function DialogFrame({
  labelledBy,
  pending = false,
  onClose,
  initialFocusRef,
  children,
  className = '',
}: DialogFrameProps) {
  const openerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusFrame = window.requestAnimationFrame(() => initialFocusRef?.current?.focus())
    return () => {
      window.cancelAnimationFrame(focusFrame)
      openerRef.current?.focus()
    }
  }, [initialFocusRef])

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && !pending) {
      event.preventDefault()
      onClose()
      return
    }
    if (event.key !== 'Tab') return

    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ))
    if (!focusable.length) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-stone-950/45 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      onKeyDown={handleKeyDown}
      onMouseDown={event => {
        if (!pending && event.target === event.currentTarget) onClose()
      }}
    >
      <div className={className}>{children}</div>
    </div>
  )
}
