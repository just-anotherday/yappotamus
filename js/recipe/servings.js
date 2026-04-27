let currentServings = 3;
const baseServings = 3;

function formatFraction(value) {
  if (value >= 0.9) return '1';
  if (value >= 0.75) return '¾';
  if (value >= 0.66) return '⅔';
  if (value >= 0.5) return '½';
  if (value >= 0.33) return '⅓';
  if (value >= 0.25) return '¼';
  if (value >= 0.125) return '⅛';
  return value.toFixed(2);
}

function updateIngredientQuantities() {
  const servingDisplay = document.getElementById('servingSize');
  if (servingDisplay) servingDisplay.textContent = currentServings;

  const scaleFactor = currentServings / baseServings;
  document.querySelectorAll('.ingredient-quantity').forEach((element) => {
    const baseValue = parseFloat(element.getAttribute('data-base'));
    let scaledValue = baseValue * scaleFactor;

    if (scaledValue % 1 !== 0) {
      if (scaledValue < 1) {
        scaledValue = formatFraction(scaledValue);
      } else {
        scaledValue = Math.round(scaledValue * 10) / 10;
      }
    }

    element.textContent = scaledValue;
  });
}

export function getCurrentServings() {
  return currentServings;
}

export function initServings() {
  const decreaseBtn = document.getElementById('decreaseServing');
  const increaseBtn = document.getElementById('increaseServing');

  const decreaseServings = () => {
    if (currentServings > 1) {
      currentServings--;
      updateIngredientQuantities();
    }
  };

  const increaseServings = () => {
    if (currentServings < 20) {
      currentServings++;
      updateIngredientQuantities();
    }
  };

  updateIngredientQuantities();

  if (decreaseBtn) decreaseBtn.addEventListener('click', decreaseServings);
  if (increaseBtn) increaseBtn.addEventListener('click', increaseServings);
}
