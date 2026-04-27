function scrollToSection(sectionId) {
  const element = document.getElementById(sectionId);
  if (!element) return;
  const offset = 80;
  const elementPosition = element.getBoundingClientRect().top;
  const offsetPosition = elementPosition + window.pageYOffset - offset;
  window.scrollTo({
    top: offsetPosition,
    behavior: 'smooth',
  });
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleBackToTopButton() {
  const backToTopButton = document.querySelector('.back-to-top');
  if (!backToTopButton) return;
  backToTopButton.style.display = window.pageYOffset > 300 ? 'block' : 'none';
}

export function initNav() {
  window.scrollToSection = scrollToSection;
  window.scrollToTop = scrollToTop;

  const jumpBtn = document.querySelector('.jump-to-recipe');
  jumpBtn?.addEventListener('click', () => {
    const target = jumpBtn.getAttribute('data-scroll-target') || 'ingredients';
    scrollToSection(target);
  });

  document.querySelector('.back-to-top')?.addEventListener('click', scrollToTop);

  window.addEventListener('scroll', toggleBackToTopButton);
  toggleBackToTopButton();
}
