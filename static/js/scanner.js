document.addEventListener('DOMContentLoaded', () => {
  const status = document.getElementById('scan-status');
  const reader = document.getElementById('qr-reader');
  if (!reader || !status) return;
  if (typeof Html5QrcodeScanner === 'undefined') {
    status.textContent = 'Camera scanner library could not load. You can open the QR pass link from the bookings table instead.'; return;
  }
  const scanner = new Html5QrcodeScanner('qr-reader', {fps: 10, qrbox: {width: 220, height: 220}, rememberLastUsedCamera: true}, false);
  scanner.render((decodedText) => {
    try {
      const url = new URL(decodedText);
      if (url.origin !== window.location.origin || !url.pathname.startsWith('/admin/scan/')) {
        status.textContent = 'This QR code is not a valid Parkwise parking pass.'; return;
      }
      status.textContent = 'QR pass recognized. Opening booking…';
      scanner.clear().then(() => window.location.assign(url.href));
    } catch (_) { status.textContent = 'Could not read this QR code. Try again.'; }
  }, () => {});
});
