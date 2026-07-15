import { Link } from 'react-router-dom'
import { catalog } from './data/catalog'

export default function RecipesPage() {
  return (
    <section className="rounded-3xl border-2 border-yellow-300 bg-zinc-100 p-6 shadow-lg md:p-8">
      <h1 className="text-4xl font-extrabold text-black md:text-5xl">Recipes Collection</h1>
      <p className="mt-2 text-zinc-600">Explore my favorite culinary creations.</p>

      <div className="mt-6 grid gap-5 md:grid-cols-2">
        {catalog.map((recipe) => (
          <article key={recipe.id} className="overflow-hidden rounded-2xl border border-black/10 bg-white shadow-sm">
            <img
              src={recipe.image}
              alt={recipe.imageAlt}
              className="h-56 w-full bg-zinc-100 object-contain p-2"
              loading="lazy"
            />
            <div className="space-y-3 p-5">
              <h2 className="text-2xl font-bold text-black">{recipe.title}</h2>
              <p className="text-zinc-600">{recipe.blurb}</p>
              <Link
                to={`/recipes/${recipe.id}`}
                className="inline-flex rounded-lg border-2 border-black bg-black px-5 py-2.5 font-bold text-white transition hover:-translate-y-0.5 hover:bg-yellow-500 hover:text-black"
              >
                View Recipe →
              </Link>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
