/**
 * FitBuddy AI – Main JavaScript
 * Global utilities, nav scroll effects, and shared interactions
 */

/* ── Navbar Scroll Effect ─────────────────────────────────── */
(function () {
  const nav = document.getElementById('mainNav');
  if (!nav) return;
  const onScroll = () => {
    nav.classList.toggle('scrolled', window.scrollY > 20);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

/* ── Intersection Observer — fade-in on scroll ────────────── */
(function () {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1 }
  );

  document.querySelectorAll('.card-fit, .feature-icon, .hero-stat').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(16px)';
    el.style.transition = 'opacity .5s ease, transform .5s ease';
    observer.observe(el);
  });

  // Once visible
  document.querySelectorAll('.card-fit, .feature-icon, .hero-stat').forEach(el => {
    const obs2 = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) {
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
        obs2.disconnect();
      }
    }, { threshold: 0.1 });
    obs2.observe(el);
  });
})();

/* ── Tooltip Init ─────────────────────────────────────────── */
(function () {
  if (typeof bootstrap !== 'undefined') {
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
      new bootstrap.Tooltip(el);
    });
  }
})();

/* ── Active Nav Link Highlight ────────────────────────────── */
(function () {
  const path  = window.location.pathname;
  const links = document.querySelectorAll('#mainNav .nav-link');
  links.forEach(link => {
    const href = link.getAttribute('href') || '';
    if (href !== '/' && path.startsWith(href)) {
      link.classList.add('active');
    }
  });
})();

/* ── Global Utility: show toast notification ──────────────── */
function showToast(message, type = 'success') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;display:flex;flex-direction:column;gap:10px;';
    document.body.appendChild(container);
  }

  const toast   = document.createElement('div');
  const bgColor = type === 'success' ? '#16a34a' : type === 'error' ? '#ef4444' : '#3b82f6';
  toast.style.cssText = `background:${bgColor};color:#fff;padding:12px 20px;border-radius:10px;
    font-size:.88rem;font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,.2);
    animation:slideUpToast .3s ease;max-width:320px;`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all .3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Inject toast animation
const style = document.createElement('style');
style.textContent = `@keyframes slideUpToast{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}`;
document.head.appendChild(style);

/* ── Global Utility: format numbers ──────────────────────── */
function formatNumber(n) {
  return Number(n).toLocaleString();
}

/* ── Progress bar animation on load ─────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.progress-fit .bar').forEach(bar => {
    const target = bar.style.width;
    bar.style.width = '0%';
    setTimeout(() => { bar.style.width = target; }, 300);
  });
});
