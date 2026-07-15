import { Link } from 'react-router-dom'

export default function PanmeeSpotlight() {
  return (
    <section className="mx-auto w-full max-w-xl rounded-2xl border-2 border-amber-300 bg-gradient-to-br from-amber-100 to-yellow-100 p-6 text-center shadow-md">
      <h2 className="text-4xl font-bold tracking-wide text-amber-900">🍜 Pan Mee Noodle Soup</h2>
      <p className="mt-2 font-['Permanent_Marker'] text-xl text-amber-700">
        One of my favorite comfort food creations.
      </p>

      <div className="mt-3 flex flex-wrap justify-center gap-2">
        {['Recipe', 'Comfort Food', 'Personal Project'].map((badge) => (
          <span
            key={badge}
            className="rounded-full border border-yellow-300 bg-black px-3 py-1 text-xs font-bold text-yellow-300"
          >
            {badge}
          </span>
        ))}
      </div>

      <div className="mx-auto mt-4 max-w-md overflow-hidden rounded-xl border border-amber-200 shadow-sm">
        <picture>
          <source
            type="image/avif"
            srcSet="/assets/panmee_photo/image002-320.avif 320w, /assets/panmee_photo/image002-384.avif 384w, /assets/panmee_photo/image002-640.avif 640w"
            sizes="(min-width: 768px) 448px, 320px"
          />
          <source
            type="image/webp"
            srcSet="/assets/panmee_photo/image002-320.webp 320w, /assets/panmee_photo/image002-384.webp 384w, /assets/panmee_photo/image002-640.webp 640w"
            sizes="(min-width: 768px) 448px, 320px"
          />
          <img
            src="/assets/panmee_photo/image002.jpg"
            alt="Pan Mee Noodle Soup"
            width="640"
            height="256"
            loading="lazy"
            decoding="async"
            className="h-64 w-full object-cover"
          />
        </picture>
      </div>

      <Link
        to="/recipes/panmee"
        className="mt-5 inline-flex rounded-lg border-2 border-black bg-black px-5 py-2.5 font-bold text-white transition hover:-translate-y-0.5 hover:bg-yellow-500 hover:text-black"
      >
        View Recipe →
      </Link>
    </section>
  )
}
