const DEFAULT_RECIPE = 'panmee';
const RECIPE_ID_PATTERN = /^[a-z0-9_-]+$/i;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatNumber(value) {
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100;
  return Number.isInteger(rounded)
    ? String(rounded)
    : String(rounded).replace(/(?:\.0+|(?<=\..*?)0+)$/, '');
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url} (${response.status})`);
  }
  return response.json();
}

async function fetchHtml(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url} (${response.status})`);
  }
  return response.text();
}

function getRecipeIdFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const recipeId = params.get('recipe');

  if (!recipeId) return DEFAULT_RECIPE;
  if (!RECIPE_ID_PATTERN.test(recipeId)) return DEFAULT_RECIPE;

  return recipeId.toLowerCase();
}

function showLoadError(message) {
  const recipeRoot = document.getElementById('recipe');
  if (!recipeRoot) return;

  recipeRoot.innerHTML = `
    <div class="recipe-load-error">
      <h2>Unable to load recipe</h2>
      <p>${escapeHtml(message)}</p>
      <p><a href="recipes.html">Back to recipes</a></p>
    </div>
  `;
}

function initServingsFeature() {
  const decreaseBtn = document.getElementById('decreaseServing');
  const increaseBtn = document.getElementById('increaseServing');
  const servingDisplay = document.getElementById('servingSize');
  const baseServingsEl = document.getElementById('baseServings');
  const quantityEls = Array.from(document.querySelectorAll('.ingredient-quantity[data-base]'));

  if (!decreaseBtn || !increaseBtn || !servingDisplay || !baseServingsEl || quantityEls.length === 0) {
    return;
  }

  const baseServings = parseFloat(baseServingsEl.textContent) || 2;
  let currentServings = parseFloat(servingDisplay.textContent) || baseServings;

  const render = () => {
    servingDisplay.textContent = formatNumber(currentServings);

    quantityEls.forEach((el) => {
      const baseQty = parseFloat(el.dataset.base || '');
      if (!Number.isFinite(baseQty)) return;

      const scaled = (baseQty / baseServings) * currentServings;
      el.textContent = formatNumber(scaled);
    });
  };

  decreaseBtn.addEventListener('click', () => {
    currentServings = Math.max(1, currentServings - 1);
    render();
  });

  increaseBtn.addEventListener('click', () => {
    currentServings = Math.min(24, currentServings + 1);
    render();
  });

  render();
}

function initModalFeature() {
  const modal = document.getElementById('imageModal');
  const modalImage = document.getElementById('modalImage');
  const closeButton = modal?.querySelector('.close');
  const galleryImages = Array.from(document.querySelectorAll('.image-gallery img'));

  if (!modal || !modalImage || !closeButton || galleryImages.length === 0) {
    return;
  }

  const closeModal = () => {
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    modalImage.removeAttribute('src');
    modalImage.setAttribute('alt', '');
  };

  const openModal = (img) => {
    modalImage.src = img.src;
    modalImage.alt = img.alt || 'Recipe image';
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
  };

  galleryImages.forEach((img) => {
    img.addEventListener('click', () => openModal(img));
  });

  closeButton.addEventListener('click', closeModal);
  modal.addEventListener('click', (event) => {
    if (event.target === modal) closeModal();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeModal();
  });
}

function initNavFeature() {
  const jumpButton = document.querySelector('.jump-to-recipe');
  const backToTopButton = document.querySelector('.back-to-top');

  if (jumpButton) {
    jumpButton.addEventListener('click', () => {
      const targetId = jumpButton.dataset.scrollTarget || 'ingredients';
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  if (backToTopButton) {
    backToTopButton.classList.add('hidden');

    backToTopButton.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    window.addEventListener('scroll', () => {
      const show = window.scrollY > 300;
      backToTopButton.classList.toggle('visible', show);
      backToTopButton.classList.toggle('hidden', !show);
    });
  }
}

function initPrintFeature() {
  const printButton = document.querySelector('.print-btn');
  if (!printButton) return;

  printButton.addEventListener('click', () => window.print());
}

function initTitleEasterEgg() {
  const titleLink = document.querySelector('.site-title a');
  if (!titleLink) return;

  let titleEggClicks = 0;
  let titleEggTimer = null;
  let titleEggActive = false;
  const originalTitle = titleLink.textContent;

  titleLink.addEventListener('click', (event) => {
    event.preventDefault();
    if (titleEggActive) return;

    titleEggClicks += 1;

    if (titleEggTimer) clearTimeout(titleEggTimer);
    titleEggTimer = setTimeout(() => {
      titleEggClicks = 0;
    }, 1600);

    if (titleEggClicks < 5) return;

    titleEggClicks = 0;
    titleEggActive = true;

    titleLink.textContent = 'yapvibes.exe';
    titleLink.classList.add('title-egg-active');

    const overlay = document.createElement('div');
    overlay.className = 'title-egg-overlay';
    overlay.innerHTML = '<div class="title-egg-flash"></div>';
    document.body.appendChild(overlay);

    document.body.classList.add('title-egg-immersive');

    if (typeof confetti === 'function') {
      confetti({ particleCount: 220, spread: 120, origin: { y: 0.6 } });
      setTimeout(() => confetti({ particleCount: 180, spread: 95, origin: { y: 0.3 } }), 300);
    }

    setTimeout(() => {
      titleLink.textContent = originalTitle;
      titleLink.classList.remove('title-egg-active');
      document.body.classList.remove('title-egg-immersive');
      overlay.remove();
      titleEggActive = false;
    }, 3600);
  });
}

function initFeatures(features) {
  if (features.includes('servings')) initServingsFeature();
  if (features.includes('modal')) initModalFeature();
  if (features.includes('nav')) initNavFeature();
  if (features.includes('print')) initPrintFeature();
}

async function loadRecipe(recipeId) {
  const manifestPath = `./${recipeId}/manifest.json`;
  const manifest = await fetchJson(manifestPath);

  if (manifest.documentTitle) {
    document.title = manifest.documentTitle;
  }

  const slots = Array.isArray(manifest.slots) ? manifest.slots : [];

  for (const slotDef of slots) {
    if (!Array.isArray(slotDef) || slotDef.length < 2) continue;

    const [slotId, relativePath] = slotDef;
    const slotEl = document.getElementById(slotId);
    if (!slotEl) continue;

    const html = await fetchHtml(`./${recipeId}/${relativePath}`);
    slotEl.innerHTML = html;
  }

  initFeatures(Array.isArray(manifest.features) ? manifest.features : []);
}

document.addEventListener('DOMContentLoaded', async () => {
  window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  const recipeId = getRecipeIdFromQuery();
  initTitleEasterEgg();

  try {
    await loadRecipe(recipeId);
  } catch (error) {
    console.error('Recipe load error:', error);
    showLoadError(error instanceof Error ? error.message : 'Unknown recipe error');
  }
});

window.addEventListener('pageshow', () => {
  window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
});
