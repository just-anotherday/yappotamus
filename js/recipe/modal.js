function openModal(src, alt = '') {
  const modal = document.getElementById('imageModal');
  const modalImage = document.getElementById('modalImage');
  if (!modal || !modalImage) return;

  modalImage.src = src;
  modalImage.alt = alt;
  modal.style.display = 'flex';
  modal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  const modal = document.getElementById('imageModal');
  const modalImage = document.getElementById('modalImage');
  if (!modal) return;

  modal.style.display = 'none';
  modal.setAttribute('aria-hidden', 'true');
  if (modalImage) {
    modalImage.removeAttribute('src');
    modalImage.alt = '';
  }
  document.body.style.overflow = 'auto';
}

export function initModal() {
  document.addEventListener('click', (e) => {
    const img = e.target.closest?.('.image-gallery img');
    if (img && img.src) openModal(img.src, img.alt || 'Recipe photo');
  });

  const modal = document.getElementById('imageModal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }

  const closeBtn = document.querySelector('#imageModal .close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => closeModal());
    closeBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        closeModal();
      }
    });
  }

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeModal();
  });
}
