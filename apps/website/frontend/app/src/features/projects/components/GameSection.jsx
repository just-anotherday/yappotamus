import { useState } from 'react'

export default function GameSection({ clickCount, onImageClick }) {
  const [gameLoaded, setGameLoaded] = useState(false)
  const imageScale = Math.min(1 + clickCount * 0.025, 1.25)
  const imageRotation = clickCount > 0 ? (clickCount % 2 === 0 ? 1 : -1) : 0

  return (
    <section className="relative rounded-3xl border-2 border-yellow-300 bg-zinc-100 p-6 shadow-lg md:p-8">
      {clickCount > 0 && clickCount < 11 && (
        <div className="absolute right-4 top-4 rounded-md bg-black px-3 py-1 font-mono text-xs text-lime-300">
          Clicks: {clickCount}/11
        </div>
      )}

      <h2 className="font-['Permanent_Marker'] text-center text-5xl text-orange-500 drop-shadow-[2px_2px_0_rgba(0,0,0,0.5)]">
        Projects
      </h2>

      <article className="mt-6 rounded-2xl border border-black/10 bg-white p-5">
        <div className="text-center">
          <h3 className="font-['Permanent_Marker'] text-4xl text-orange-500">slimeScraper</h3>
          <p className="font-['Bebas_Neue'] text-2xl tracking-[0.2em] text-amber-600">a Unity Game Project</p>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {['Unity', 'C#', 'Procedural Generation', 'WebGL'].map((badge) => (
              <span
                key={badge}
                className="rounded-full border border-yellow-300 bg-black px-3 py-1 text-xs font-bold text-yellow-300"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>

        <button
          type="button"
          onClick={onImageClick}
          className="mx-auto mt-4 block overflow-hidden rounded-2xl border border-black/20"
        >
          <picture>
            <source
              type="image/avif"
              srcSet="/assets/slimeScraper-256.avif 256w, /assets/slimeScraper-384.avif 384w, /assets/slimeScraper-512.avif 512w, /assets/slimeScraper-768.avif 768w"
              sizes="(min-width: 1024px) 768px, (min-width: 768px) 384px, 256px"
            />
            <source
              type="image/webp"
              srcSet="/assets/slimeScraper-256.webp 256w, /assets/slimeScraper-384.webp 384w, /assets/slimeScraper-512.webp 512w, /assets/slimeScraper-768.webp 768w"
              sizes="(min-width: 1024px) 768px, (min-width: 768px) 384px, 256px"
            />
            <img
              src="/assets/slimeScraper.jpg"
              alt="slimeScraper Screenshot"
              width="768"
              height="256"
              fetchPriority="high"
              loading="eager"
              decoding="async"
              className="h-64 w-full max-w-4xl object-cover object-top transition duration-200"
              style={{ transform: `scale(${imageScale}) rotate(${imageRotation}deg)`, transition: 'transform 200ms ease-out' }}
            />
          </picture>
        </button>

        <p className="mt-4 text-center text-zinc-700">
          A Unity-built roguelike FPS Prototype that generates random office floors each run. Built
          with C# and Unity within 4 weeks.
        </p>

        <div className="mt-6 rounded-xl bg-zinc-50 p-4 text-center">
          <h4 className="text-xl font-bold text-black">🎮 Play slimeScraper in Browser</h4>

          {!gameLoaded ? (
            <div className="mt-3 space-y-3">
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-700">
                <p className="font-semibold">⚠️ Large File Warning</p>
                <p className="mt-1 text-sm">
                  This WebGL game is ~25MB and may take time to load. Please use a stable internet
                  connection.
                </p>
                <p className="mt-1 text-xs">Game has bugs, sorry in advance if you almost beat it!</p>
              </div>

              <button
                type="button"
                onClick={() => setGameLoaded(true)}
                className="rounded-lg bg-emerald-600 px-6 py-3 font-bold text-white transition hover:bg-emerald-700"
              >
                🎮 Click to Load Game
              </button>
              <p className="text-sm text-zinc-500">WebGL Game - Click to load when ready</p>
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              <div className="overflow-hidden rounded-xl border border-black/10 bg-white p-3">
                <iframe
                  title="slimeScraper"
                  frameBorder="0"
                  src="https://itch.io/embed-upload/15262394?color=333333"
                  allowFullScreen
                  className="h-[450px] w-full md:h-[640px]"
                />
                <p className="mt-2 text-sm">
                  <a
                    href="https://jasonzyap.itch.io/slimescraper"
                    target="_blank"
                    rel="noreferrer"
                    className="font-semibold text-blue-700 underline-offset-4 hover:underline"
                  >
                    Play slimeScraper on itch.io
                  </a>
                </p>
              </div>

              <button
                type="button"
                onClick={() => setGameLoaded(false)}
                className="rounded-lg bg-red-600 px-4 py-2 font-semibold text-white transition hover:bg-red-700"
              >
                ❌ Unload Game
              </button>
            </div>
          )}
        </div>

        <div className="mt-6 text-center">
          <a
            href="https://drive.google.com/file/d/1tJ365BaZsQgmfNjmVbuYB9oV0fFNqPYQ/view?usp=drive_link"
            target="_blank"
            rel="noreferrer"
            className="inline-flex rounded-lg border-2 border-black bg-black px-5 py-2.5 font-bold text-white transition hover:-translate-y-0.5 hover:bg-yellow-500 hover:text-black"
          >
            ⬇️ Download Game via Google Drive (.zip)
          </a>
          <p className="mt-2 text-sm text-zinc-600">
            After downloading, extract the ZIP and double-click the <code>.exe</code> to play.
          </p>
        </div>
      </article>
    </section>
  )
}
