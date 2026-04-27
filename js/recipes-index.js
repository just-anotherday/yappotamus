const CATALOG_URL = new URL('../recipes/catalog.json', import.meta.url);

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function recipeHref(id) {
  return `../html/recipe.html?recipe=${encodeURIComponent(id)}`;
}

async function init() {
  const root = document.getElementById('recipe-catalog');
  if (!root) return;

  try {
    const res = await fetch(CATALOG_URL);
    if (!res.ok) throw new Error('Catalog unavailable');
    const data = await res.json();
    const items = Array.isArray(data.recipes) ? data.recipes : [];

    if (items.length === 0) {
      root.innerHTML = '<p class="instructions">No recipes in catalog yet.</p>';
      return;
    }

    root.innerHTML = items
      .map(
        (r) => `
        <article class="recipe-hero" data-recipe-id="${escapeHtml(r.id)}">
          <img src="${escapeHtml(r.image)}" alt="${escapeHtml(r.imageAlt || r.title)}" loading="lazy" />
          <div class="recipe-hero-content">
            <h3>${escapeHtml(r.title)}</h3>
            <p>${escapeHtml(r.blurb || '')}</p>
            <a href="${recipeHref(r.id)}" class="recipe-link">View Recipe →</a>
          </div>
        </article>`
      )
      .join('');
  } catch (e) {
    console.error(e);
    root.innerHTML =
      '<p class="instructions">Could not load the recipe list. Open a recipe directly, e.g. <a href="../html/recipe.html?recipe=panmee">Pan Mee</a>.</p>';
  }
}

document.addEventListener('DOMContentLoaded', init);
