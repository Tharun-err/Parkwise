const form = document.getElementById('availability-form');
const results = document.getElementById('slot-results');
const message = document.getElementById('slot-message');
const startInput = document.getElementById('start-time');
const endInput = document.getElementById('end-time');
const vehicleInput = document.getElementById('vehicle-number');

function makeLocalValue(date) {
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return adjusted.toISOString().slice(0, 16);
}
if (startInput && endInput) {
  const start = new Date(); start.setMinutes(start.getMinutes() + 60); start.setMinutes(0, 0, 0);
  const end = new Date(start); end.setHours(end.getHours() + 2);
  startInput.value = makeLocalValue(start);
  endInput.value = makeLocalValue(end);
}

async function checkAvailability(event) {
  if (event) event.preventDefault();
  results.innerHTML = '';
  const start = startInput.value;
  const end = endInput.value;
  if (!start || !end || new Date(end) <= new Date(start) || new Date(start) <= new Date()) {
    message.textContent = 'Choose a future arrival time and a later departure time.';
    return;
  }

  message.textContent = 'Checking spaces…';
  try {
    const response = await fetch(`${window.PARKWISE.slotsUrl}?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not load spaces.');

    const availableCount = data.filter(slot => slot.available).length;
    const occupiedCount = data.filter(slot => slot.active && !slot.available).length;
    const disabledCount = data.filter(slot => !slot.active).length;
    message.textContent = `${availableCount} available · ${occupiedCount} occupied · ${disabledCount} under maintenance · ${data.length} total spaces.`;

    if (!data.length) {
      results.innerHTML = '<div class="empty-inline">No active parking spaces are configured.</div>';
      return;
    }

    // Show every active slot so users can distinguish free spaces from occupied ones.
    data.forEach(slot => {
      const card = document.createElement('div');
      card.className = `slot-result-card ${slot.available ? 'slot-available' : 'slot-occupied'}`;

      const rate = document.createElement('span');
      rate.className = 'slot-result-rate';
      rate.textContent = `₹${slot.rate}/hr`;

      const code = document.createElement('strong');
      code.textContent = slot.code;

      const detail = document.createElement('small');
      detail.textContent = `${slot.vehicle_type} · Zone ${slot.zone}`;

      const status = document.createElement('span');
      status.className = `slot-availability-label ${slot.available ? 'is-available' : 'is-occupied'}`;
      status.textContent = slot.available ? 'Available' : (slot.active ? 'Occupied' : 'Maintenance');

      card.append(code, rate, detail, status);

      if (slot.available) {
        const button = document.createElement('button');
        button.className = 'btn btn-dark btn-small';
        button.textContent = 'Reserve ↗';
        button.addEventListener('click', () => submitBooking(slot.id));
        card.appendChild(button);
      } else {
        const unavailable = document.createElement('button');
        unavailable.className = 'btn btn-small slot-unavailable-button';
        unavailable.textContent = 'Not available';
        unavailable.disabled = true;
        unavailable.setAttribute('aria-label', `${slot.code} is not available and cannot be reserved`);
        card.appendChild(unavailable);
      }

      results.appendChild(card);
    });
  } catch (error) {
    message.textContent = error.message;
  }
}

form?.addEventListener('submit', checkAvailability);
let availabilityRefresh = null;
form?.addEventListener('submit', () => {
  if (availabilityRefresh) clearInterval(availabilityRefresh);
  availabilityRefresh = setInterval(() => checkAvailability(), 15000);
});

function submitBooking(slotId) {
  const vehicle = vehicleInput.value.trim().toUpperCase();
  if (!vehicle) {
    message.textContent = 'Enter your vehicle number before reserving.';
    vehicleInput.focus();
    return;
  }
  const post = document.createElement('form');
  post.method = 'post';
  post.action = window.PARKWISE.bookUrl;
  const values = {slot_id: slotId, start: startInput.value, end: endInput.value, vehicle_number: vehicle};
  Object.entries(values).forEach(([name, value]) => {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = value;
    post.appendChild(input);
  });
  document.body.appendChild(post);
  post.submit();
}
