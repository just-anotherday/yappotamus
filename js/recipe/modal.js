function openModal(src) {
  const modal = document.getElementById('imageModal');
  const modalImage = document.getElementById('modalImage');
  if (!modal || !modalImage) return;
  modal.style.display = 'block';
  modalImage.src = src;
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  const modal = document.getElementById('imageModal');
  if (!modal) return;
  modal.style.display = 'none';
  document.body.style.overflow = 'auto';
}

export function initModal() {
  window.openModal = openModal;
  window.closeModal = closeModal;

  document.addEventListener('click', (e) => {
    const img = e.target.closest?.('.image-gallery img');
    if (img && img.src) openModal(img.src);
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
