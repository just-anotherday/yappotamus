const DEFAULT_RECIPE_ID = 'panmee';

function getRecipeId() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get('recipe')?.trim();
  return id || DEFAULT_RECIPE_ID;
}

function recipeBaseUrl(recipeId) {
  return new URL(`../recipes/${recipeId}/`, window.location.href).toString();
}

async function loadManifest(recipeId) {
  const base = recipeBaseUrl(recipeId);
  const res = await fetch(new URL('manifest.json', base));
  if (!res.ok) throw new Error(`Recipe "${recipeId}" not found (missing manifest).`);
  const manifest = await res.json();
  if (manifest.id && manifest.id !== recipeId) {
    console.warn(`Recipe folder "${recipeId}" manifest id is "${manifest.id}"`);
  }
  return { base, manifest };
}

async function loadSlots(base, slots) {
  for (const entry of slots) {
    const [elementId, relativePath] = entry;
    const el = document.getElementById(elementId);
    if (!el) {
      console.warn(`Missing slot #${elementId}`);
      continue;
    }
    const url = new URL(relativePath, base).toString();
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to load ${relativePath}`);
    el.innerHTML = await res.text();
  }
}

function showError(message) {
  const err = document.getElementById('recipe-error');
  if (!err) return;
  err.textContent = message;
  err.hidden = false;
}

async function runFeature(name) {
  if (name === 'servings') {
    const { initServings, getCurrentServings } = await import('./recipe/servings.js');
    initServings();
    return { getCurrentServings };
  }
  if (name === 'modal') {
    const { initModal } = await import('./recipe/modal.js');
    initModal();
    return {};
  }
  if (name === 'nav') {
    const { initNav } = await import('./recipe/nav.js');
    initNav();
    return {};
  }
  if (name === 'print') {
    return {};
  }
  return {};
}

async function init() {
  const recipeId = getRecipeId();
  let manifest;

  try {
    const loaded = await loadManifest(recipeId);
    manifest = loaded.manifest;
    await loadSlots(loaded.base, manifest.slots || []);
  } catch (e) {
    console.error(e);
    showError(e.message || 'Could not load this recipe.');
    return;
  }

  if (manifest.documentTitle) {
    document.title = manifest.documentTitle;
  }

  const features = Array.isArray(manifest.features) ? manifest.features : [];
  let getCurrentServings = () => 3;

  for (const feature of features) {
    const result = await runFeature(feature);
    if (typeof result.getCurrentServings === 'function') {
      getCurrentServings = result.getCurrentServings;
    }
  }

  if (features.includes('print')) {
    const { initPrint } = await import('./recipe/print.js');
    initPrint({ getCurrentServings });
  }

  document.querySelector('.print-btn')?.addEventListener('click', () => window.print());
}

document.addEventListener('DOMContentLoaded', init);
