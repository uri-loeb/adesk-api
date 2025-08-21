
// static/landing.js
document.addEventListener('DOMContentLoaded', () => {
  const payBtn = document.getElementById('payBtn');
  const note = document.getElementById('note');
  if (!payBtn) return;

  payBtn.addEventListener('click', async () => {
    try {
      const res = await fetch('/create-checkout-session', { method: 'POST' });
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        note.textContent = data.error || 'Failed to start checkout.';
      }
    } catch (e) {
      note.textContent = 'Network error starting checkout.';
    }
  });
});
