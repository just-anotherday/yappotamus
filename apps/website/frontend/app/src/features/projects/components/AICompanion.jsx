import { useEffect, useMemo, useRef, useState } from 'react'

const COOLDOWN_MS = 3000
const LIMIT_WINDOW_MS = 30_000
const MAX_MESSAGES_PER_WINDOW = 3
const API_URL = import.meta.env.VITE_AI_API_BASE || 'https://api.yapvibes.com/api/openai'

function formatTime(seconds) {
  return Math.max(0, Math.ceil(seconds)).toFixed(2)
}

function getFallbackResponse(message) {
  const lowerMessage = message.toLowerCase()

  if (lowerMessage.includes('hello') || lowerMessage.includes('hi') || lowerMessage.includes('hey')) {
    return "Hello! I'm currently in offline mode. When the AI service is available, I can help with creative writing, coding, analysis, and much more!"
  }
  if (lowerMessage.includes('weather')) {
    return "I can't check real-time weather data right now, but sunny days are great for outdoor activities!"
  }
  if (lowerMessage.includes('joke') || lowerMessage.includes('funny')) {
    const jokes = [
      "Why don't scientists trust atoms? Because they make up everything!",
      'Why did the scarecrow win an award? He was outstanding in his field!',
      'What do you call a fake noodle? An impasta!',
    ]
    return jokes[Math.floor(Math.random() * jokes.length)]
  }
  if (lowerMessage.includes('help')) {
    return "I'd love to help! While I'm in offline mode, I can provide general information and examples."
  }
  if (lowerMessage.includes('code') || lowerMessage.includes('programming')) {
    return "Here's a simple Python example:\n\nprint('yapvibes!')\n\nWhen online, I can help with more complex programming questions too!"
  }

  const genericResponses = [
    'Interesting! I am in offline fallback mode right now, but I can still share general guidance.',
    'Great prompt — I can answer in more depth once the hosted AI endpoint responds again.',
    'The AI service appears unavailable at the moment, so I am giving a fallback response.',
  ]
  return genericResponses[Math.floor(Math.random() * genericResponses.length)]
}

export default function AICompanion() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldownUntil, setCooldownUntil] = useState(0)
  const [messageTimestamps, setMessageTimestamps] = useState([])
  const [backendStatus, setBackendStatus] = useState('unknown')
  const [tick, setTick] = useState(Date.now())
  const [secretPhrase, setSecretPhrase] = useState('')
  const [isImmersiveUnlocked, setIsImmersiveUnlocked] = useState(false)
  const [hasTriggeredLimitEgg, setHasTriggeredLimitEgg] = useState(false)
  const [isExplosionActive, setIsExplosionActive] = useState(false)
  const [explosionUntil, setExplosionUntil] = useState(0)
  const deephouseAudioRef = useRef(null)
  const hasPlayedYapvibesRef = useRef(false)

  useEffect(() => {
    const audio = new Audio('/assets/edm-song-yapvibes.mp3')
    audio.volume = 0.35
    deephouseAudioRef.current = audio

    return () => {
      if (deephouseAudioRef.current) {
        deephouseAudioRef.current.pause()
        deephouseAudioRef.current.currentTime = 0
      }
      deephouseAudioRef.current = null
    }
  }, [])

  // Drive a live countdown ticker every 50ms
  useEffect(() => {
    if (document.getElementById('yap-react-explosion-style')) return
    const style = document.createElement('style')
    style.id = 'yap-react-explosion-style'
    style.textContent = `
      @keyframes yapReactExplosionPulse {
        0% { opacity: 1; transform: translate(-50%, -50%) scale(0.2); }
        100% { opacity: 0; transform: translate(-50%, -50%) scale(2.6); }
      }
    `
    document.head.appendChild(style)
  }, [])

  useEffect(() => {
    const id = setInterval(() => setTick(Date.now()), 50)
    return () => clearInterval(id)
  }, [])

  const activeTimestamps = useMemo(
    () => messageTimestamps.filter((timestamp) => tick - timestamp < LIMIT_WINDOW_MS),
    [messageTimestamps, tick],
  )

  const messagesLeft = Math.max(0, MAX_MESSAGES_PER_WINDOW - activeTimestamps.length)
  const cooldownRemaining = Math.max(0, (cooldownUntil - tick) / 1000)
  const resetInSeconds =
    activeTimestamps.length > 0
      ? Math.max(0, (LIMIT_WINDOW_MS - (tick - activeTimestamps[0])) / 1000)
      : 0

  const isOnCooldown = cooldownRemaining > 0
  const isRateLimited = messagesLeft === 0
  const isBlocked = isOnCooldown || isRateLimited || loading
  const showSecretPrompt = isRateLimited

  useEffect(() => {
    if (!isRateLimited) {
      setSecretPhrase('')
      setIsImmersiveUnlocked(false)
      setHasTriggeredLimitEgg(false)
      setExplosionUntil(0)
      setIsExplosionActive(false)
    }
  }, [isRateLimited])

  useEffect(() => {
    if (isRateLimited && !hasTriggeredLimitEgg) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'ai',
          sender: 'yapBot Secret',
          content: '🥚 Easter Egg Unlocked: You used all 3 messages. Cooldown activated until the rate window resets.',
        },
      ])
      setHasTriggeredLimitEgg(true)
    }
  }, [isRateLimited, hasTriggeredLimitEgg])

  useEffect(() => {
    if (!isImmersiveUnlocked) return
    setIsExplosionActive(true)
    setExplosionUntil(Date.now() + resetInSeconds * 1000)
  }, [isImmersiveUnlocked, resetInSeconds])

  useEffect(() => {
    if (!isExplosionActive || !explosionUntil) return
    if (Date.now() >= explosionUntil) {
      setIsExplosionActive(false)
      setIsImmersiveUnlocked(false)
      return
    }
    const intervalId = setInterval(() => {
      if (Date.now() >= explosionUntil) {
        clearInterval(intervalId)
        setIsExplosionActive(false)
        setIsImmersiveUnlocked(false)
      }
    }, 100)
    return () => clearInterval(intervalId)
  }, [isExplosionActive, explosionUntil])

  const cooldownMessage = isRateLimited
    ? `Rate limited — window resets in ${formatTime(resetInSeconds)}s`
    : isOnCooldown
      ? `Please wait ${formatTime(cooldownRemaining)}s before sending again`
      : null

  const pingBackend = async () => {
    setBackendStatus('checking')

    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 6000)

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'ping', context: [] }),
        signal: controller.signal,
      })

      clearTimeout(timeout)
      setBackendStatus(response.ok ? 'online' : 'offline')
      return response.ok
    } catch {
      setBackendStatus('offline')
      return false
    }
  }

  const sendMessage = async () => {
    const content = input.trim()
    if (!content || loading) return

    if (
      content.toLowerCase() === 'yapvibes' &&
      deephouseAudioRef.current &&
      !hasPlayedYapvibesRef.current &&
      deephouseAudioRef.current.paused
    ) {
      hasPlayedYapvibesRef.current = true
      deephouseAudioRef.current.currentTime = 0
      deephouseAudioRef.current.play().catch(() => {})
    }

    const currentTime = Date.now()
    const pruned = messageTimestamps.filter((timestamp) => currentTime - timestamp < LIMIT_WINDOW_MS)

    if (pruned.length >= MAX_MESSAGES_PER_WINDOW) {
      setMessages((prev) => [
        ...prev,
        { role: 'ai', sender: 'Limit', content: 'Message limit reached. Please wait for the window to reset.' },
      ])
      return
    }

    if (currentTime < cooldownUntil) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'ai',
          sender: 'Cooldown',
          content: `Please wait ${Math.ceil((cooldownUntil - currentTime) / 1000)}s before sending another message.`,
        },
      ])
      return
    }

    setMessageTimestamps([...pruned, currentTime])
    setMessages((prev) => [...prev, { role: 'user', content }])
    setInput('')
    setLoading(true)

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: content,
          context: messages.slice(-6).map((message) => ({
            role: message.role === 'user' ? 'user' : 'assistant',
            content: message.content,
          })),
        }),
      })

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setBackendStatus('online')

      const data = await response.json()
      if (!data?.reply) throw new Error('Invalid response payload')

      setMessages((prev) => [...prev, { role: 'ai', sender: 'yapBot', content: data.reply }])
    } catch {
      setBackendStatus('offline')
      setMessages((prev) => [
        ...prev,
        { role: 'ai', sender: 'Offline Bot', content: getFallbackResponse(content) },
      ])
    } finally {
      setLoading(false)
      setCooldownUntil(Date.now() + COOLDOWN_MS)
    }
  }

  return (
    <section className="rounded-3xl border-2 border-yellow-300 bg-zinc-100 p-6 shadow-lg md:p-8">
      <h2 className="font-['Permanent_Marker'] text-center text-4xl text-orange-500">Chat Companion</h2>
      <p className="mt-2 text-center text-sm font-semibold tracking-wide text-transparent bg-gradient-to-r from-amber-500 via-orange-500 to-yellow-500 bg-clip-text">
        AI Generated text responses using OpenAI models.
      </p>

      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <span
          className={`rounded-full border px-3 py-1 text-xs font-bold ${
            backendStatus === 'online'
              ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
              : backendStatus === 'offline'
                ? 'border-red-300 bg-red-50 text-red-700'
                : backendStatus === 'checking'
                  ? 'border-blue-300 bg-blue-50 text-blue-700'
                  : 'border-yellow-300 bg-yellow-100 text-amber-700'
          }`}
        >
          {backendStatus === 'online' && 'Backend: Online'}
          {backendStatus === 'offline' && 'Backend: Offline (fallback mode)'}
          {backendStatus === 'checking' && 'Backend: Checking...'}
          {backendStatus === 'unknown' && 'Backend: Unknown'}
        </span>

        <button
          type="button"
          onClick={() => {
            void pingBackend()
          }}
          disabled={backendStatus === 'checking'}
          className="rounded-full border border-black/15 bg-white px-3 py-1 text-xs font-bold text-zinc-700 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Reconnect
        </button>
      </div>

      <div className="mt-4 flex flex-wrap justify-center gap-2">
        {['AI', 'OpenAI', 'Node.js', 'API'].map((badge) => (
          <span
            key={badge}
            className="rounded-full border border-yellow-300 bg-black px-3 py-1 text-xs font-bold text-yellow-300"
          >
            {badge}
          </span>
        ))}
      </div>

      <div className="mt-5 overflow-hidden rounded-xl border border-black/10 bg-white">
        <div className="max-h-[340px] min-h-[260px] space-y-3 overflow-y-auto bg-zinc-50 p-4">
          {messages.length === 0 && (
            <p className="text-center text-sm text-zinc-500">Say hi to start chatting with yapBot.</p>
          )}

          {messages.map((message, index) => (
            <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm ${
                  message.role === 'user'
                    ? 'rounded-br-md bg-blue-600 text-white'
                    : 'rounded-bl-md border border-black/10 bg-white text-zinc-700'
                }`}
              >
                {message.role === 'ai' && message.sender ? (
                  <div className="mb-1 text-[11px] font-bold text-zinc-500">🤖 {message.sender}</div>
                ) : null}
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="rounded-2xl rounded-bl-md border border-black/10 bg-white px-3.5 py-2 text-sm text-zinc-700">
                <div className="mb-1 text-[11px] font-bold text-zinc-500">🤖 Thinking...</div>
                <div className="flex gap-1">
                  <span className="typing-dot" />
                  <span className="typing-dot [animation-delay:0.2s]" />
                  <span className="typing-dot [animation-delay:0.4s]" />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-black/10 bg-white p-4">
          {/* Cooldown / Rate Limit notification */}
          {cooldownMessage && (
            <div className="mb-3 flex items-center justify-center gap-3 rounded-xl border border-orange-300 bg-orange-50 px-4 py-4 text-center">
              <svg className="h-6 w-6 animate-spin text-orange-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm font-bold text-orange-700">{cooldownMessage}</span>
            </div>
          )}

          {showSecretPrompt && (
            <div className="mb-3 rounded-xl border border-purple-300 bg-purple-50 p-3">
              <p className="mb-2 text-xs font-bold uppercase tracking-wide text-purple-700">
                Secret phrase challenge
              </p>
              <p className="mb-2 text-xs font-semibold text-purple-600">Hint: code is <span className="font-bold">yapvibes</span></p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  type="text"
                  value={secretPhrase}
                  onChange={(event) => setSecretPhrase(event.target.value)}
                  placeholder="Enter secret phrase (yapvibes)"
                  className="w-full rounded-lg border border-purple-300 bg-white px-3 py-2 text-sm text-purple-900 outline-none ring-purple-300 focus:ring"
                  disabled={isImmersiveUnlocked}
                />
                <button
                  type="button"
                  onClick={() => {
                    if (secretPhrase.trim().toLowerCase() === 'yapvibes') {
                      setIsImmersiveUnlocked(true)
                    }
                  }}
                  disabled={isImmersiveUnlocked}
                  className="rounded-lg bg-purple-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Unlock
                </button>
              </div>
            </div>
          )}

          {isImmersiveUnlocked && (
            <div className="relative mb-3 overflow-hidden rounded-xl border border-fuchsia-300 bg-gradient-to-r from-fuchsia-500 via-purple-500 to-indigo-500 p-4 text-white shadow-lg">
              <div className="pointer-events-none absolute inset-0 opacity-30">
                <div className="absolute -left-8 top-2 h-8 w-8 animate-bounce rounded-full bg-white/70" />
                <div className="absolute left-1/3 top-6 h-4 w-4 animate-pulse rounded-full bg-yellow-200" />
                <div className="absolute right-8 top-3 h-6 w-6 animate-bounce rounded-full bg-cyan-200 [animation-delay:0.2s]" />
                <div className="absolute bottom-3 left-1/4 h-5 w-5 animate-pulse rounded-full bg-pink-200 [animation-delay:0.3s]" />
                <div className="absolute bottom-2 right-1/4 h-3 w-3 animate-bounce rounded-full bg-lime-200 [animation-delay:0.4s]" />
              </div>
              <p className="relative text-center font-['Permanent_Marker'] text-3xl tracking-widest drop-shadow-md">
                YAPVIBES UNLOCKED
              </p>
              <p className="relative mt-1 text-center text-xs font-semibold uppercase tracking-wide text-fuchsia-100">
                Immersive mode active while you wait...
              </p>
            </div>
          )}

          {isExplosionActive && (
            <div className="pointer-events-none fixed inset-0 z-[9999] overflow-hidden">
              <div className="absolute inset-0 animate-pulse bg-[radial-gradient(circle_at_center,rgba(255,120,0,0.85)_0%,rgba(255,40,0,0.55)_35%,rgba(10,0,0,0.92)_100%)]" />
              {Array.from({ length: 18 }).map((_, index) => (
                <span
                  // eslint-disable-next-line react/no-array-index-key
                  key={index}
                  className="absolute rounded-full opacity-90"
                  style={{
                    left: `${Math.random() * 100}%`,
                    top: `${Math.random() * 100}%`,
                    width: `${80 + Math.random() * 260}px`,
                    height: `${80 + Math.random() * 260}px`,
                    transform: 'translate(-50%, -50%)',
                    background:
                      'radial-gradient(circle, rgba(255,255,180,0.95) 0%, rgba(255,120,0,0.82) 45%, rgba(255,0,0,0) 75%)',
                    animation: `yapReactExplosionPulse ${700 + Math.random() * 900}ms ease-out forwards`,
                  }}
                />
              ))}
            </div>
          )}

          {/* Always-visible rate limit status */}
          <div className="mb-3 flex justify-end">
            <span
              className={`rounded-full border px-3 py-1 text-[11px] font-bold ${
                isRateLimited
                  ? 'border-red-200 bg-red-50 text-red-700'
                  : isOnCooldown
                    ? 'border-orange-200 bg-orange-50 text-orange-700'
                    : 'border-yellow-300 bg-yellow-100 text-amber-800'
              }`}
            >
              {messagesLeft} / {MAX_MESSAGES_PER_WINDOW} messages • {isRateLimited ? `reset ${formatTime(resetInSeconds)}s` : isOnCooldown ? `cooldown ${formatTime(cooldownRemaining)}s` : 'ready'}
            </span>
          </div>

          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void sendMessage()
              }
            }}
            className={`min-h-[90px] w-full resize-y rounded-xl border px-3 py-2 text-sm outline-none ring-yellow-300 transition focus:ring ${
              isBlocked ? 'cursor-not-allowed border-red-200 bg-red-50 text-zinc-400' : 'border-black/15 bg-white'
            }`}
            placeholder={isBlocked ? 'Please wait...' : 'Type your message here...'}
            disabled={isBlocked}
          />

          <button
            type="button"
            disabled={isBlocked}
            onClick={() => {
              void sendMessage()
            }}
            className={`mt-3 ml-auto block rounded-full px-5 py-2 font-extrabold shadow transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60 ${
              isBlocked
                ? 'bg-zinc-300 text-zinc-500'
                : 'bg-gradient-to-r from-orange-500 to-yellow-400 text-zinc-900'
            }`}
          >
            {loading ? 'Sending...' : isOnCooldown ? 'Cooldown...' : 'Send It'}
          </button>
        </div>
      </div>
    </section>
  )
}









