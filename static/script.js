async function fetchStatus() {
    const res = await fetch('/api/status');
    const data = await res.json();
  
    const container = document.getElementById('parking-slots');
    container.innerHTML = '';
  
    data.fields.forEach(slot => {
      const div = document.createElement('div');
      div.classList.add('slot');
      if (slot.status === 1) div.classList.add('occupied');
  
      div.innerHTML = `
        <span class="slot-id">Slot ${slot.slot}</span>
        <span class="status">${slot.status === 1 ? 'Occupied' : 'Available'}</span>
      `;
      container.appendChild(div);
    });
  }
  
  fetchStatus();
  setInterval(fetchStatus, 30000); // refresh every 30s
  