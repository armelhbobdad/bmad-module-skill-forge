/**
 * Mermaid Diagram Lightbox
 * Click any rendered mermaid diagram to view it fullscreen.
 * Press Escape or click the backdrop to close.
 */
(function () {
  const overlay = document.createElement('div');
  overlay.className = 'mermaid-lightbox';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', 'Diagram fullscreen view');
  overlay.innerHTML =
    '<div class="mermaid-lightbox-content"></div>' +
    '<button class="mermaid-lightbox-close" aria-label="Close">&times;</button>' +
    '<span class="mermaid-lightbox-hint">Click anywhere or press Esc to close</span>';
  document.body.appendChild(overlay);

  const content = overlay.querySelector('.mermaid-lightbox-content');

  function open(svg) {
    content.innerHTML = '';
    var clone = svg.cloneNode(true);
    // Remove fixed dimensions so CSS can scale the SVG to fill the viewport
    clone.removeAttribute('width');
    clone.removeAttribute('height');
    clone.removeAttribute('style');
    // Ensure viewBox exists for proper scaling
    if (!clone.getAttribute('viewBox') && svg.viewBox && svg.viewBox.baseVal) {
      var vb = svg.viewBox.baseVal;
      if (vb.width && vb.height) {
        clone.setAttribute('viewBox', vb.x + ' ' + vb.y + ' ' + vb.width + ' ' + vb.height);
      }
    }
    if (!clone.getAttribute('viewBox')) {
      // Fallback: use the rendered bounding box
      var bbox = svg.getBBox();
      clone.setAttribute('viewBox', bbox.x + ' ' + bbox.y + ' ' + bbox.width + ' ' + bbox.height);
    }
    content.appendChild(clone);
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function close() {
    overlay.classList.remove('active');
    document.body.style.overflow = '';
    content.innerHTML = '';
  }

  // Event delegation — works regardless of when mermaid renders
  document.addEventListener('click', function (e) {
    var target = e.target.closest('pre.mermaid');
    if (target) {
      var svg = target.querySelector('svg');
      if (svg) open(svg);
    }
  });

  overlay.addEventListener('click', function (e) {
    // Close unless clicking inside the SVG itself
    if (!e.target.closest('svg')) close();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay.classList.contains('active')) close();
  });
})();
