// Recipe scaling functionality
let currentServings = 3;
const baseServings = 3;

// DOM elements
const servingDisplay = document.getElementById('servingSize');
const decreaseBtn = document.getElementById('decreaseServing');
const increaseBtn = document.getElementById('increaseServing');

// Initialize
document.addEventListener('DOMContentLoaded', function() {
  updateIngredientQuantities();
  
  // Event listeners for serving buttons
  if (decreaseBtn) decreaseBtn.addEventListener('click', decreaseServings);
  if (increaseBtn) increaseBtn.addEventListener('click', increaseServings);
  
  // Show/hide back to top button based on scroll
  window.addEventListener('scroll', toggleBackToTopButton);
});

// Function to decrease servings
function decreaseServings() {
  if (currentServings > 1) {
    currentServings--;
    updateIngredientQuantities();
  }
}

// Function to increase servings
function increaseServings() {
  if (currentServings < 20) {
    currentServings++;
    updateIngredientQuantities();
  }
}

// Function to update all ingredient quantities
function updateIngredientQuantities() {
  if (servingDisplay) servingDisplay.textContent = currentServings;
  
  const scaleFactor = currentServings / baseServings;
  const quantityElements = document.querySelectorAll('.ingredient-quantity');
  quantityElements.forEach(element => {
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

// Function to format fractions for cooking measurements
function formatFraction(value) {
  if (value >= 0.9) return "1";
  if (value >= 0.75) return "¾";
  if (value >= 0.66) return "⅔";
  if (value >= 0.5) return "½";
  if (value >= 0.33) return "⅓";
  if (value >= 0.25) return "¼";
  if (value >= 0.125) return "⅛";
  return value.toFixed(2);
}

// Modal functions
function openModal(src) {
  document.getElementById('imageModal').style.display = 'block';
  document.getElementById('modalImage').src = src;
  document.body.style.overflow = 'hidden'; // Prevent background scrolling
}

function closeModal() {
  document.getElementById('imageModal').style.display = 'none';
  document.body.style.overflow = 'auto'; // Re-enable scrolling
}

// Close modal when clicking outside the image
window.onclick = function(event) {
  const modal = document.getElementById('imageModal');
  if (event.target == modal) {
    closeModal();
  }
}

// Close modal with Escape key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeModal();
  }
});

// Navigation functions
function scrollToSection(sectionId) {
  const element = document.getElementById(sectionId);
  if (element) {
    const offset = 80;
    const elementPosition = element.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - offset;
    
    window.scrollTo({
      top: offsetPosition,
      behavior: 'smooth'
    });
  }
}

function scrollToTop() {
  window.scrollTo({
    top: 0,
    behavior: 'smooth'
  });
}

// Show/hide back to top button based on scroll position
function toggleBackToTopButton() {
  const backToTopButton = document.querySelector('.back-to-top');
  if (backToTopButton) {
    if (window.pageYOffset > 300) {
      backToTopButton.style.display = 'block';
    } else {
      backToTopButton.style.display = 'none';
    }
  }
}

// Print functionality enhancement
function setupPrintEnhancement() {
  // Add print event listener to update servings before printing
  window.addEventListener('beforeprint', function() {
    // Update the displayed serving size for print
    const printServings = document.createElement('div');
    printServings.className = 'print-serving-info';
    printServings.innerHTML = `<p><strong>Recipe scaled for: ${currentServings} servings</strong></p>`;
    document.querySelector('.serving-selector').appendChild(printServings);
  });
}

// Initialize print enhancement
setupPrintEnhancement();