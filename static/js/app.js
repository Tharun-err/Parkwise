document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input[type="datetime-local"]').forEach(input => {
    const now = new Date(); now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    input.min = now.toISOString().slice(0, 16);
  });
  const today = document.getElementById('today-label');
  if (today) today.textContent = new Intl.DateTimeFormat('en-IN', {weekday:'long', month:'short', day:'numeric'}).format(new Date()).toUpperCase();
});


// Parkwise interaction polish: password visibility, strength feedback and gentle reveals.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      button.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      button.setAttribute('aria-pressed', String(show));
      const label = button.querySelector('.toggle-label');
      if (label) label.textContent = show ? 'Hide' : 'Show';
      button.classList.toggle('is-visible', show);
    });
  });

  const password = document.getElementById('password');
  const fill = document.getElementById('meter-fill');
  const meterLabel = document.getElementById('meter-label');
  if (password && fill && meterLabel) {
    password.addEventListener('input', () => {
      const value = password.value;
      let score = 0;
      if (value.length >= 8) score++;
      if (/[A-Z]/.test(value)) score++;
      if (/[0-9]/.test(value)) score++;
      if (/[^A-Za-z0-9]/.test(value)) score++;
      const levels = [
        ['0%', 'Use at least 8 characters'],
        ['25%', 'Keep going — add more variety'],
        ['50%', 'Getting stronger'],
        ['75%', 'Strong password'],
        ['100%', 'Excellent password']
      ];
      fill.style.width = levels[score][0];
      fill.dataset.level = String(score);
      meterLabel.textContent = levels[score][1];
    });
  }

  const form = document.getElementById('auth-form');
  if (form) {
    form.addEventListener('submit', event => {
      const first = document.getElementById('password');
      const confirm = document.getElementById('confirm-password');
      if (first && confirm && first.value !== confirm.value) {
        event.preventDefault();
        confirm.setCustomValidity('Passwords do not match.');
        confirm.reportValidity();
      } else if (confirm) {
        confirm.setCustomValidity('');
      }
    });
    const confirm = document.getElementById('confirm-password');
    if (confirm) confirm.addEventListener('input', () => confirm.setCustomValidity(''));
  }

  const revealTargets = document.querySelectorAll('.hero-copy, .hero-visual, .feature-strip > div, .bottom-cta, .section-block, .stat-card, .auth-showcase, .auth-panel-inner, .qr-card, .pass-copy, .scanner-panel, .slot-admin-card');
  revealTargets.forEach((element, index) => {
    element.classList.add('reveal-ready');
    element.style.setProperty('--reveal-delay', `${Math.min(index % 4, 3) * 75}ms`);
  });
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    revealTargets.forEach(element => observer.observe(element));
  } else {
    revealTargets.forEach(element => element.classList.add('is-revealed'));
  }
});
