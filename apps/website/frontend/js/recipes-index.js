function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function createRecipeCard(recipe) {
  const id = recipe.id || '';
  const title = recipe.title || 'Untitled Recipe';
  const blurb = recipe.blurb || '';
  const image = recipe.image || '';
  const imageAlt = recipe.imageAlt || title;

  return `
    <article class="recipe-hero">
      <img src="${escapeHtml(image)}" alt="${escapeHtml(imageAlt)}" loading="lazy" />
      <div class="recipe-hero-content">
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(blurb)}</p>
        <a class="recipe-link" href="recipe.html?recipe=${encodeURIComponent(id)}">View Recipe →</a>
      </div>
    </article>
  `;
}

async function loadRecipeCatalog() {
  const target = document.getElementById('recipe-catalog');
  if (!target) return;

  try {
    const response = await fetch('./catalog.json');
    if (!response.ok) {
      throw new Error(`Failed to load catalog (${response.status})`);
    }

    const data = await response.json();
    const recipes = Array.isArray(data.recipes) ? data.recipes : [];

    if (recipes.length === 0) {
      target.innerHTML = '<p class="coming-soon">No recipes listed yet.</p>';
      return;
    }

    target.innerHTML = recipes.map(createRecipeCard).join('\n');
  } catch (error) {
    console.error('Recipe catalog load error:', error);
    target.innerHTML = `
      <div class="recipe-load-error">
        <h3>Unable to load recipes right now.</h3>
        <p>Please try refreshing the page.</p>
      </div>
    `;
  }
}

document.addEventListener('DOMContentLoaded', loadRecipeCatalog);

window.addEventListener('pageshow', () => {
  window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
});
