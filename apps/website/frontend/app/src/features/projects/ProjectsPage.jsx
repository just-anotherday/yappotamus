import { useEffect } from 'react'
import AICompanion from './components/AICompanion'
import GameSection from './components/GameSection'
import PanmeeSpotlight from './components/PanmeeSpotlight'
import { useNuclearEgg } from './hooks/useNuclearEgg'
import { createSecretSequenceHandler } from '../../lib/secretSequence'

function NuclearOverlay({ floatingEmojis }) {
  return (
    <div className="pointer-events-none fixed right-3 top-24 z-50 w-[220px] rounded-2xl border-2 border-yellow-300 bg-black/85 p-4 text-yellow-300 shadow-2xl md:w-[260px]">
      <div className="text-center">
        <p className="text-2xl font-black tracking-[0.18em] md:text-3xl">YAPVIBES</p>
        <p className="mt-2 text-5xl">😎</p>
        <p className="mt-1 text-xs font-semibold text-yellow-200/90">Mode Active</p>
      </div>

      {floatingEmojis.map((emoji) => (
        <span
          key={emoji.id}
          className="emoji-float absolute text-2xl md:text-3xl"
          style={{
            left: `${emoji.left}%`,
            top: `${emoji.top}%`,
            animationDuration: `${emoji.duration}s`,
          }}
        >
          {emoji.symbol}
        </span>
      ))}
    </div>
  )
}

export default function ProjectsPage() {
  const { active, clickCount, registerClick, floatingEmojis } = useNuclearEgg()

  useEffect(() => {
    const onWpmKeyDown = createSecretSequenceHandler({
      sequence: 'wpm',
      onMatch: () => {
        window.location.href = '/wpm'
      },
      idleResetMs: 1500,
      lockoutMs: 500,
    })

    const onHomeKeyDown = createSecretSequenceHandler({
      sequence: 'home',
      onMatch: () => {
        window.location.href = '/'
      },
      idleResetMs: 1500,
      lockoutMs: 500,
    })

    document.addEventListener('keydown', onWpmKeyDown)
    document.addEventListener('keydown', onHomeKeyDown)
    return () => {
      document.removeEventListener('keydown', onWpmKeyDown)
      document.removeEventListener('keydown', onHomeKeyDown)
    }
  }, [])

  return (
    <div className="space-y-6">
      {active ? <NuclearOverlay floatingEmojis={floatingEmojis} /> : null}
      <GameSection clickCount={clickCount} onImageClick={registerClick} />
      <PanmeeSpotlight />
      <AICompanion isYapvibesModeActive={active} />
    </div>
  )
}
