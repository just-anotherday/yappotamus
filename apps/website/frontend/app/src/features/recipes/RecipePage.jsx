import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { formatNumber } from '../../lib/number'
import { panmeeRecipe } from './data/panmeeRecipe'

const recipeMap = {
  panmee: panmeeRecipe,
}

function RecipeImage({ src, alt, onOpen }) {
  return (
    <button
      type="button"
      onClick={() => onOpen({ src, alt })}
      className="overflow-hidden rounded-xl border border-black/10 bg-zinc-100"
    >
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className="h-48 w-full object-contain p-2 transition hover:scale-[1.01]"
      />
    </button>
  )
}

function StepCard({ step, onOpen }) {
  return (
    <article className="rounded-xl border border-black/10 bg-white p-4">
      <h4 className="text-xl font-bold text-black">{step.title}</h4>
      <p className="mt-2 text-zinc-700">{step.text}</p>
      {step.images.length > 0 && (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {step.images.map((image) => (
            <RecipeImage key={image.src} src={image.src} alt={image.alt} onOpen={onOpen} />
          ))}
        </div>
      )}
    </article>
  )
}

export default function RecipePage() {
  const { recipeId = 'panmee' } = useParams()
  const recipe = recipeMap[recipeId]

  const [servings, setServings] = useState(recipe?.baseServings ?? 2)
  const [modalImage, setModalImage] = useState(null)
  const [showTop, setShowTop] = useState(false)

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 300)
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    if (!recipe) return
    document.title = `Jason Yap | ${recipeId === 'panmee' ? 'Pan Mee Recipe' : 'Recipe'}`
  }, [recipe, recipeId])

  const servingRatio = useMemo(() => servings / (recipe?.baseServings ?? 2), [servings, recipe])

  if (!recipe) {
    return (
      <section className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700">
        <h2 className="text-2xl font-bold">Unable to load recipe</h2>
        <p className="mt-2">Recipe id: {recipeId}</p>
        <Link to="/recipes" className="mt-3 inline-flex font-semibold underline">
          Back to recipes
        </Link>
      </section>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap justify-between gap-3">
        <button
          type="button"
          onClick={() => document.getElementById('ingredients')?.scrollIntoView({ behavior: 'smooth' })}
          className="rounded-lg border-2 border-black bg-black px-5 py-2 font-bold text-white transition hover:bg-yellow-500 hover:text-black"
        >
          Jump to Recipe
        </button>

        {showTop && (
          <button
            type="button"
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
            className="rounded-lg border-2 border-yellow-300 bg-yellow-300 px-5 py-2 font-bold text-black transition hover:bg-black hover:text-yellow-300"
          >
            ↑ Back to Top
          </button>
        )}
      </div>

      <section className="rounded-3xl border-2 border-yellow-300 bg-zinc-100 p-6 shadow-lg md:p-8">
        <h1 className="bg-gradient-to-r from-yellow-300 via-amber-400 to-red-500 bg-clip-text text-4xl font-black uppercase tracking-[0.08em] leading-tight text-transparent drop-shadow-[0_10px_22px_rgba(194,65,12,0.35)] md:text-6xl">
          {recipe.title}
        </h1>
        <p className="mt-2 text-sm font-bold text-zinc-600">{recipe.author}</p>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {recipe.heroImages.map((image) => (
            <RecipeImage key={image.src} src={image.src} alt={image.alt} onOpen={setModalImage} />
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-black/10 bg-white p-5" id="introduction">
        <h2 className="border-l-4 border-yellow-400 pl-3 text-2xl font-black uppercase tracking-[0.06em] text-black">INTRODUCTION</h2>
        <p className="mt-3 text-zinc-700">{recipe.intro}</p>
        <p className="mt-3 font-bold text-zinc-700">{recipe.cookTime}</p>

        <div className="mt-4 rounded-xl border border-black/10 bg-zinc-50 p-4">
          <h3 className="font-black uppercase tracking-[0.04em] text-black">Adjust Serving Size:</h3>
          <div className="mt-2 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setServings((value) => Math.max(1, value - 1))}
              className="h-10 w-10 rounded-lg border border-black/20 bg-white text-xl font-bold"
            >
              -
            </button>
            <div className="min-w-16 rounded-lg border border-black/20 bg-white px-4 py-2 text-center font-bold text-black">
              {formatNumber(servings)}
            </div>
            <button
              type="button"
              onClick={() => setServings((value) => Math.min(24, value + 1))}
              className="h-10 w-10 rounded-lg border border-black/20 bg-white text-xl font-bold"
            >
              +
            </button>
          </div>
          <p className="mt-2 text-sm text-zinc-600">Base recipe is for {recipe.baseServings} servings.</p>
        </div>
      </section>

      <section className="rounded-2xl border border-black/10 bg-white p-5">
        <h3 className="border-l-4 border-yellow-400 pl-3 text-xl font-black uppercase tracking-[0.05em] text-black">Jump to Section</h3>
        <ul className="mt-2 space-y-1 text-sm">
          {['introduction', 'ingredients', 'preparation', 'instructions', 'assembly', 'notes'].map((section) => (
            <li key={section}>
              <a href={`#${section}`} className="font-semibold text-blue-700 underline-offset-4 hover:underline">
                {section[0].toUpperCase() + section.slice(1)}
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section id="ingredients" className="rounded-2xl border border-black/10 bg-white p-5">
        <h2 className="border-l-4 border-yellow-400 pl-3 text-2xl font-black uppercase tracking-[0.06em] text-black">INGREDIENTS</h2>
        <div className="mt-4 space-y-4">
          {recipe.ingredients.map((group) => (
            <article key={group.title} className="rounded-xl border border-black/10 bg-zinc-50 p-4">
              <h4 className="font-black uppercase tracking-[0.04em] text-black">{group.title}</h4>
              <ul className="mt-2 space-y-2">
                {group.items.map((item, index) => (
                  <li key={`${group.title}-${index}`} className="flex items-start gap-2 text-zinc-700">
                    <input type="checkbox" className="mt-1" />
                    <span>
                      {typeof item.amount === 'number'
                        ? `${formatNumber(item.amount * servingRatio)}${item.unit ? ` ${item.unit}` : ''} `
                        : ''}
                      {item.label}
                    </span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section id="preparation" className="rounded-2xl border border-black/10 bg-white p-5">
        <h2 className="border-l-4 border-yellow-400 pl-3 text-2xl font-black uppercase tracking-[0.06em] text-black">PREPARATION</h2>
        <div className="mt-3 space-y-2 text-zinc-700">
          {recipe.preparation.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {recipe.preparation.images.map((image) => (
            <RecipeImage key={image.src} src={image.src} alt={image.alt} onOpen={setModalImage} />
          ))}
        </div>
      </section>

      <section id="instructions" className="rounded-2xl border border-black/10 bg-white p-5">
        <h2 className="border-l-4 border-yellow-400 pl-3 text-2xl font-black uppercase tracking-[0.06em] text-black">INSTRUCTIONS</h2>
        <div className="mt-4 space-y-4">
          {recipe.instructions.map((step) => (
            <StepCard key={step.title} step={step} onOpen={setModalImage} />
          ))}
        </div>
      </section>

      <section id="assembly" className="rounded-2xl border border-black/10 bg-white p-5">
        <h2 className="border-l-4 border-yellow-400 pl-3 text-2xl font-black uppercase tracking-[0.06em] text-black">ASSEMBLY</h2>
        <div className="mt-4 space-y-4">
          {recipe.assembly.map((step) => (
            <StepCard key={step.title} step={step} onOpen={setModalImage} />
          ))}
        </div>
      </section>

      <section id="notes" className="rounded-2xl border border-black/10 bg-white p-5">
        <h2 className="border-l-4 border-yellow-400 pl-3 text-2xl font-black uppercase tracking-[0.06em] text-black">NOTES</h2>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-zinc-700">
          {recipe.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>

        <button
          type="button"
          onClick={() => window.print()}
          className="mt-4 rounded-lg border-2 border-black bg-black px-5 py-2 font-bold text-white transition hover:bg-yellow-500 hover:text-black"
        >
          Print Recipe
        </button>
      </section>

      {modalImage && (
        <div
          role="button"
          tabIndex={0}
          onClick={() => setModalImage(null)}
          onKeyDown={(event) => {
            if (event.key === 'Escape' || event.key === 'Enter') setModalImage(null)
          }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4"
        >
          <button
            type="button"
            onClick={() => setModalImage(null)}
            className="absolute right-4 top-4 rounded-full bg-white px-3 py-1 text-lg font-bold text-black"
          >
            ×
          </button>
          <img
            src={modalImage.src}
            alt={modalImage.alt}
            className="max-h-[90vh] max-w-[95vw] rounded-lg border border-white/30 shadow-2xl"
          />
        </div>
      )}
    </div>
  )
}
