export function initPrint({ getCurrentServings }) {
  window.addEventListener('beforeprint', () => {
    const selector = document.querySelector('.serving-selector');
    if (!selector || typeof getCurrentServings !== 'function') return;

    selector.querySelector('.print-serving-info')?.remove();

    const printServings = document.createElement('div');
    printServings.className = 'print-serving-info';
    printServings.innerHTML = `<p><strong>Recipe scaled for: ${getCurrentServings()} servings</strong></p>`;
    selector.appendChild(printServings);
  });
}
