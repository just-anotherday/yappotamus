export function initPrint({ getCurrentServings }) {
  window.addEventListener('beforeprint', () => {
    const recipeHeader = document.getElementById('recipe-header');
    if (!recipeHeader || typeof getCurrentServings !== 'function') return;

    document.querySelector('.print-serving-info')?.remove();

    const printServings = document.createElement('div');
    printServings.className = 'print-serving-info';
    printServings.innerHTML = `<p><strong>Recipe scaled for: ${getCurrentServings()} servings</strong></p>`;
    recipeHeader.appendChild(printServings);
  });
}
