export function createSecretSequenceHandler({
  sequence,
  onMatch,
  idleResetMs = 1500,
  lockoutMs = 500,
}) {
  const normalized = String(sequence || '').toLowerCase()
  let buffer = ''
  let idleTimer = null
  let lockoutUntil = 0

  const resetBuffer = () => {
    buffer = ''
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  return (event) => {
    if (!normalized) return
    if (event.ctrlKey || event.metaKey || event.altKey) return
    if (event.key.length !== 1) return

    const key = event.key.toLowerCase()
    if (!/[a-z]/.test(key)) return

    const now = Date.now()
    if (now < lockoutUntil) return

    buffer = `${buffer}${key}`.slice(-normalized.length)

    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(resetBuffer, idleResetMs)

    if (buffer !== normalized) return

    lockoutUntil = now + lockoutMs
    resetBuffer()
    onMatch?.()
  }
}
