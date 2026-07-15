import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createSecretSequenceHandler } from '../../lib/secretSequence'

const starsByRow = [6, 5, 6, 5, 6, 5, 6, 5, 6]

function hideFlagOverPhoto(photo) {
  const existingFlag = document.querySelector('.photo-flag')
  if (existingFlag) existingFlag.remove()
  photo.style.visibility = 'visible'
}

function showFlagOverPhoto(photo, durationMs) {
  const rect = photo.getBoundingClientRect()
  photo.style.visibility = 'hidden'

  const flag = document.createElement('div')
  flag.className = 'photo-flag'
  flag.style.width = `${rect.width * 1.3}px`
  flag.style.height = `${rect.height * 1.3}px`
  flag.style.top = `${rect.top + window.scrollY + rect.height / 2 - (rect.height * 1.5) / 2}px`
  flag.style.left = `${rect.left + window.scrollX + rect.width / 2 - (rect.width * 1.5) / 2}px`

  const canton = document.createElement('div')
  canton.className = 'flag-canton'
  for (let row = 0; row < 9; row += 1) {
    const rowDiv = document.createElement('div')
    rowDiv.className = 'star-row'
    const starCount = row % 2 === 0 ? 6 : 5
    for (let i = 0; i < starCount; i += 1) {
      const star = document.createElement('span')
      star.className = 'flag-star'
      star.textContent = '★'
      rowDiv.appendChild(star)
    }
    canton.appendChild(rowDiv)
  }
  flag.appendChild(canton)

  const glow = document.createElement('div')
  glow.className = 'flag-glow'
  flag.appendChild(glow)

  const pole = document.createElement('div')
  pole.className = 'flag-pole'
  flag.appendChild(pole)

  for (let i = 0; i < 14; i += 1) {
    const particle = document.createElement('span')
    particle.className = 'flag-particle'
    particle.style.left = `${Math.random() * 100}%`
    particle.style.top = `${Math.random() * 100}%`
    particle.style.animationDelay = `${(Math.random() * 1.6).toFixed(2)}s`
    particle.style.animationDuration = `${(2.6 + Math.random() * 1.8).toFixed(2)}s`
    flag.appendChild(particle)
  }

  document.body.appendChild(flag)

  setTimeout(() => {
    hideFlagOverPhoto(photo)
  }, durationMs)
}

export default function HomePage() {
  const [saluteCount, setSaluteCount] = useState(0)
  const [isArmySongPlaying, setIsArmySongPlaying] = useState(false)
  const [flagClickCount, setFlagClickCount] = useState(0)
  const [flagSequencePlaying, setFlagSequencePlaying] = useState(false)
  const firstCallRef = useRef(null)
  const retreatCallRef = useRef(null)
  const armySongRef = useRef(null)
  const retreatTimerRef = useRef(null)
  const flagHideTimerRef = useRef(null)
  const profilePhotoRef = useRef(null)

  const flagThreshold = flagSequencePlaying ? 2 : 3

  const stopFlagAudioSequence = () => {
    firstCallRef.current?.pause()
    retreatCallRef.current?.pause()
    if (firstCallRef.current) firstCallRef.current.currentTime = 0
    if (retreatCallRef.current) retreatCallRef.current.currentTime = 0

    if (retreatTimerRef.current) {
      clearTimeout(retreatTimerRef.current)
      retreatTimerRef.current = null
    }
    if (flagHideTimerRef.current) {
      clearTimeout(flagHideTimerRef.current)
      flagHideTimerRef.current = null
    }

    if (profilePhotoRef.current) {
      hideFlagOverPhoto(profilePhotoRef.current)
    }
    setSaluteCount(0)
    setFlagSequencePlaying(false)
    setFlagClickCount(0)
  }

  const stopArmySong = () => {
    if (!armySongRef.current) return
    armySongRef.current.pause()
    armySongRef.current.currentTime = 0
    setIsArmySongPlaying(false)
  }

  const stopAllEasterEggMedia = () => {
    stopFlagAudioSequence()
    stopArmySong()
  }

  useEffect(() => {
    const firstCall = new Audio('/assets/FirstCall.mp3')
    const retreatCall = new Audio('/assets/retreat.mp3')
    const armySong = new Audio('/assets/THE_ARMY_SONG_BAND.MP3?v=20260506')
    firstCall.volume = 0.3
    retreatCall.volume = 0.3
    armySong.volume = 0.3
    firstCallRef.current = firstCall
    retreatCallRef.current = retreatCall
    armySongRef.current = armySong

    return () => {
      if (retreatTimerRef.current) {
        clearTimeout(retreatTimerRef.current)
        retreatTimerRef.current = null
      }
      if (flagHideTimerRef.current) {
        clearTimeout(flagHideTimerRef.current)
        flagHideTimerRef.current = null
      }

      const existingFlag = document.querySelector('.photo-flag')
      if (existingFlag) existingFlag.remove()
      if (profilePhotoRef.current) {
        profilePhotoRef.current.style.visibility = 'visible'
      }

      firstCall.pause()
      retreatCall.pause()
      armySong.pause()
      firstCallRef.current = null
      retreatCallRef.current = null
      armySongRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!armySongRef.current) return
    armySongRef.current.onended = () => {
      setIsArmySongPlaying(false)
    }
  }, [])

  useEffect(() => {
    const handlePageHide = () => {
      stopAllEasterEggMedia()
    }

    window.addEventListener('pagehide', handlePageHide)
    window.addEventListener('beforeunload', handlePageHide)

    return () => {
      window.removeEventListener('pagehide', handlePageHide)
      window.removeEventListener('beforeunload', handlePageHide)
    }
  }, [])

  useEffect(() => {
    const onProjectsKeyDown = createSecretSequenceHandler({
      sequence: 'projects',
      onMatch: () => {
        window.location.href = '/projects'
      },
      idleResetMs: 1500,
      lockoutMs: 500,
    })

    const onWpmKeyDown = createSecretSequenceHandler({
      sequence: 'wpm',
      onMatch: () => {
        window.location.href = '/wpm'
      },
      idleResetMs: 1500,
      lockoutMs: 500,
    })

    document.addEventListener('keydown', onProjectsKeyDown)
    document.addEventListener('keydown', onWpmKeyDown)
    return () => {
      document.removeEventListener('keydown', onProjectsKeyDown)
      document.removeEventListener('keydown', onWpmKeyDown)
    }
  }, [])

  useEffect(() => {
    if (saluteCount !== 3) return
    const profilePhoto = profilePhotoRef.current
    if (!profilePhoto) return

    stopFlagAudioSequence()

    if (firstCallRef.current) {
      firstCallRef.current.currentTime = 0
      firstCallRef.current.play().catch(() => {})
    }

    retreatTimerRef.current = setTimeout(() => {
      if (retreatCallRef.current) {
        retreatCallRef.current.currentTime = 0
        retreatCallRef.current.play().catch(() => {})
      }
    }, 9000)

    const fallbackFlagDurationMs = 15000
    const retreatDurationMs =
      retreatCallRef.current && Number.isFinite(retreatCallRef.current.duration)
        ? retreatCallRef.current.duration * 1000
        : 6000
    const totalSequenceMs = 9000 + retreatDurationMs

    if (retreatCallRef.current) {
      retreatCallRef.current.onended = () => {
        hideFlagOverPhoto(profilePhoto)
        setSaluteCount(0)
        setFlagSequencePlaying(false)
        setFlagClickCount(0)
      }
    }

    // Fallback in case ended event doesn't fire.
    flagHideTimerRef.current = setTimeout(() => {
      hideFlagOverPhoto(profilePhoto)
      setSaluteCount(0)
      setFlagSequencePlaying(false)
      setFlagClickCount(0)
    }, totalSequenceMs || fallbackFlagDurationMs)

    showFlagOverPhoto(profilePhoto, totalSequenceMs || fallbackFlagDurationMs)
    const activeFlag = document.querySelector('.photo-flag')
    if (activeFlag) {
      activeFlag.setAttribute('role', 'button')
      activeFlag.setAttribute('tabindex', '0')
      activeFlag.setAttribute('aria-label', 'Stop flag audio')
      activeFlag.addEventListener('click', stopFlagAudioSequence)
      activeFlag.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          stopFlagAudioSequence()
        }
      })
    }

    const closeTimer = setTimeout(() => {
      // Keep animation reset separate; flag visibility is tied to audio completion.
    }, 2000)

    return () => clearTimeout(closeTimer)
  }, [saluteCount])

  const handlePhotoClick = () => {
    const nextCount = flagClickCount + 1
    const threshold = flagSequencePlaying ? 2 : 3
    if (nextCount < threshold) {
      setFlagClickCount(nextCount)
      return
    }

    if (!flagSequencePlaying) {
      setFlagClickCount(0)
      setFlagSequencePlaying(true)
      setSaluteCount(3)
      return
    }

    stopFlagAudioSequence()
  }

  const featuredProjects = useMemo(
    () => [
      {
        title: 'slimeScraper',
        blurb:
          'A Unity-built roguelike FPS prototype featuring procedural office floors and WebGL browser play.',
        badges: ['Unity', 'C#', 'Procedural Generation', 'WebGL'],
      },
      {
        title: 'Chat Companion',
        blurb: 'An AI chat project connected to a backend service for generated text responses.',
        badges: ['AI', 'Node.js', 'OpenAI', 'API'],
      },
    ],
    [],
  )

  return (
    <div className="space-y-7">
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-3 top-3 z-[12000] -translate-y-1 rounded-full border border-amber-700/35 bg-amber-50/95 px-3 py-1.5 text-xs font-bold text-amber-900 opacity-0 shadow transition"
      >
        
      </div>

      <section className="rounded-3xl border-2 border-yellow-300 bg-gradient-to-br from-black to-zinc-900 px-6 py-10 text-center text-white shadow-xl md:px-10">
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.25em] text-yellow-300 md:text-sm">
          Think • Design • Create — the Yap way
        </p>
        <h1 className="text-4xl font-extrabold leading-tight text-yellow-300 md:text-6xl">Hi, I'm Jason Yap.</h1>
        <p className="mx-auto mt-5 max-w-3xl text-base text-zinc-100 md:text-lg">
          I build practical software, AI-powered tools, and interactive projects with a focus on
          reliability, creativity, and real-world impact.
        </p>
      </section>

      <section className="rounded-3xl border-2 border-yellow-300 bg-zinc-100 p-6 shadow-lg md:p-8">
        <div className="flex flex-col items-center gap-7 md:flex-row md:items-start">
          <div className="relative shrink-0">
            <button
              type="button"
              onClick={handlePhotoClick}
              className="relative overflow-hidden rounded-[999px] border-4 border-yellow-300 shadow-lg"
            >
              <picture>
                <source
                  type="image/avif"
                  srcSet="/assets/tempProfilePhoto-288.avif 288w, /assets/tempProfilePhoto-432.avif 432w"
                  sizes="(min-width: 768px) 288px, 240px"
                />
                <source
                  type="image/webp"
                  srcSet="/assets/tempProfilePhoto-288.webp 288w, /assets/tempProfilePhoto-432.webp 432w"
                  sizes="(min-width: 768px) 288px, 240px"
                />
                <img
                  ref={profilePhotoRef}
                  src="/assets/tempProfilePhoto.jpg"
                  alt="Jason Yap Photo"
                  width="288"
                  height="288"
                  fetchPriority="high"
                  loading="eager"
                  decoding="async"
                  className="h-60 w-60 object-cover md:h-72 md:w-72"
                />
              </picture>
            </button>
            <p className="mt-2 min-h-5 text-center text-xs font-semibold text-zinc-500" aria-live="polite">
              {flagClickCount > 0
                ? `Flag ${flagSequencePlaying ? 'OFF' : 'ON'}: ${flagClickCount}/${flagThreshold}`
                : ''}
            </p>
          </div>

          <div className="space-y-4 text-zinc-700">
            <h2 className="inline-block border-b-2 border-yellow-300 pb-1 text-2xl font-bold text-black">
              About Me
            </h2>
            <p>
              I recently graduated from <strong>University of Central Florida</strong> with a{' '}
              <strong>Bachelor of Science in Computer Science</strong> in 2026. I’m looking for a
              full-time software engineering role where I can apply my skills, grow as a developer,
              and contribute to impactful projects.
            </p>
            <p>
              My background includes{' '}
              <span className="relative z-[2] inline-flex rounded-md bg-yellow-300/20 px-1">
                <button
                  type="button"
                  onClick={() => {
                    if (!armySongRef.current) return
                    if (isArmySongPlaying) {
                      stopArmySong()
                      return
                    }

                    armySongRef.current.pause()
                    armySongRef.current.currentTime = 0
                    armySongRef.current
                      .play()
                      .then(() => {
                        setIsArmySongPlaying(true)
                      })
                      .catch(() => {
                        setIsArmySongPlaying(false)
                      })
                  }}
                  aria-label="Toggle Army song easter egg"
                  className="inline cursor-pointer border-0 bg-transparent p-0 font-inherit text-inherit underline decoration-dotted underline-offset-2 hover:text-zinc-900 focus-visible:text-zinc-900"
                >
                  U.S. Army
                </button>{' '}
              </span>{' '}
              service at <em>Fort Bragg</em>, where I developed
              leadership, resilience, and the ability to perform under pressure. Today, I’m
              passionate about <strong>AI</strong>, <strong>backend development</strong>, and{' '}
              <strong>building software that solves real-world problems</strong>.
            </p>
            <p>
              I’m excited to apply my technical skills and work ethic as part of a long-term team
              where I can grow, contribute, and build meaningful software throughout my career.
            </p>
          </div>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <section className="rounded-2xl border-2 border-yellow-300 bg-zinc-100 p-6 text-center shadow">
          <h2 className="inline-block border-b-2 border-yellow-300 pb-1 text-2xl font-bold text-black">
            Resume
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-zinc-600">You can view or download my resume below:</p>
          <a
            href="/assets/yapResume.pdf"
            target="_blank"
            rel="noreferrer"
            className="mt-5 inline-flex rounded-lg border-2 border-black bg-black px-5 py-2.5 font-bold text-white transition hover:-translate-y-0.5 hover:bg-yellow-500 hover:text-black"
          >
            View Resume
          </a>
        </section>

        <section className="rounded-2xl border-2 border-yellow-300 bg-white p-6 text-center shadow">
          <h2 className="inline-block border-b-2 border-yellow-300 pb-1 text-2xl font-bold text-black">
            Support
          </h2>
          <p className="mt-3 text-zinc-600">Donate, if you like. ✌️</p>
          <a
            href="https://www.buymeacoffee.com/jasonnyapp7"
            target="_blank"
            rel="noreferrer"
            className="mt-5 inline-flex rounded-lg border-2 border-yellow-300 bg-yellow-300 px-5 py-2.5 font-bold text-black transition hover:-translate-y-0.5 hover:bg-black hover:text-yellow-300"
          >
            Buy me a coffee
          </a>
        </section>
      </div>

      <section className="rounded-3xl border-2 border-yellow-300 bg-zinc-100 p-6 text-center shadow-lg md:p-8">
        <h2 className="inline-block border-b-2 border-yellow-300 pb-1 text-2xl font-bold text-black">
          Featured Work
        </h2>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {featuredProjects.map((project) => (
            <article key={project.title} className="rounded-2xl border border-black/10 bg-white p-5 text-left">
              <h3 className="text-xl font-bold text-black">{project.title}</h3>
              <p className="mt-2 text-zinc-600">{project.blurb}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {project.badges.map((badge) => (
                  <span
                    key={`${project.title}-${badge}`}
                    className="rounded-full border border-yellow-300 bg-black px-3 py-1 text-xs font-bold text-yellow-300"
                  >
                    {badge}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
        <Link
          to="/projects"
          className="mt-6 inline-flex rounded-lg border-2 border-black bg-black px-5 py-2.5 font-bold text-white transition hover:-translate-y-0.5 hover:bg-yellow-500 hover:text-black"
        >
          Explore All Projects
        </Link>
      </section>

    </div>
  )
}
