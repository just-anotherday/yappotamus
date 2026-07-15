import { useEffect, useMemo, useState } from 'react'

const emojiPool = ['😎', '😎', '😎', '🎉', '✨', '🪩', '🥳']

export function useNuclearEgg() {
  const [clickCount, setClickCount] = useState(0)
  const [active, setActive] = useState(false)

  const floatingEmojis = useMemo(
    () =>
      Array.from({ length: active ? 20 : 0 }).map((_, index) => ({
        id: index,
        symbol: emojiPool[Math.floor(Math.random() * emojiPool.length)],
        left: Math.random() * 100,
        top: Math.random() * 100,
        duration: 2 + Math.random() * 2,
      })),
    [active],
  )

  useEffect(() => {
    if (!active) return

    const sounds = [
      'https://assets.mixkit.co/sfx/preview/mixkit-explosion-video-game-sound-3120.mp3',
      'https://assets.mixkit.co/sfx/preview/mixkit-bomb-explosion-in-the-air-2800.mp3',
      'https://assets.mixkit.co/sfx/preview/mixkit-alarm-siren-1003.mp3',
    ]

    const players = sounds.map((src, i) => {
      const audio = new Audio(src)
      audio.volume = 0.25
      setTimeout(() => {
        audio.play().catch(() => {})
      }, i * 450)
      return audio
    })

    return () => {
      players.forEach((audio) => {
        audio.pause()
      })
      setActive(false)
      setClickCount(0)
    }
  }, [active])

  const registerClick = () => {
    if (active) return

    setClickCount((current) => {
      const next = current + 1
      if (next >= 11) {
        setActive(true)
      }
      return next
    })
  }

  return {
    active,
    clickCount,
    registerClick,
    floatingEmojis,
  }
}
