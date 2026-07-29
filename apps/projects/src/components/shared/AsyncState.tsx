export function LoadingState({ label }: { label: string }) {
  return (
    <div className="grid min-h-80 place-items-center" role="status" aria-live="polite">
      <div className="text-center">
        <div className="mx-auto mb-3 size-8 animate-pulse rounded-lg bg-emerald-700" />
        <p className="text-sm font-medium text-stone-500">{label}</p>
      </div>
    </div>
  )
}

export function RecoverableError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
    >
      <strong>Could not sync this directory.</strong> {message}
    </div>
  )
}
