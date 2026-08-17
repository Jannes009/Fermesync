document.addEventListener('DOMContentLoaded', () => {
  const editBtn = document.getElementById('edit-chemstock-btn');
  const modal = document.getElementById('edit-chemstock-modal');
  const cancelBtn = document.getElementById('cancel-edit-chemstock');
  const saveBtn = document.getElementById('save-edit-chemstock');
  const addCropBtn = document.getElementById('add-crop-row');
  const cropRows = document.getElementById('crop-rows');
  const inputActive = document.getElementById('edit-active');
  const inputColour = document.getElementById('edit-colour');

  if (!editBtn) return;

  let OPTIONS = null;

  function createCropRow(crop) {
    const row = document.createElement('div');
    row.className = 'crop-row';
    row.style.display = 'grid';
    row.style.gridTemplateColumns = '2fr 1fr 140px 1fr auto';
    row.style.gap = '8px';

    // Crop select
    const cropSelect = document.createElement('select');
    cropSelect.style.padding = '8px';
    cropSelect.style.border = '1px solid var(--border)';
    cropSelect.style.borderRadius = '6px';
    cropSelect.innerHTML = '<option value="">(select crop)</option>';
    (OPTIONS?.crops || []).forEach(o => {
      const opt = document.createElement('option');
      opt.value = o.IdCrop || o.idCrop || o.id || o[0];
      opt.textContent = o.CropDescription || o.CropCode || o.cCrop || Object.values(o).join(' ');
      cropSelect.appendChild(opt);
    });
    if (crop && (crop.CropId || crop.CropDescription)) {
      // prefer preselect by id, fallback to text
      if (crop.CropId) {
        Array.from(cropSelect.options).forEach(opt => { if (String(opt.value) === String(crop.CropId)) opt.selected = true; });
      } else {
        Array.from(cropSelect.options).forEach(opt => { if (opt.textContent === crop.CropDescription) opt.selected = true; });
      }
    }

    // Reg number
    const regInput = document.createElement('input');
    regInput.placeholder = 'Reg number';
    regInput.style.padding = '8px';
    regInput.style.border = '1px solid var(--border)';
    regInput.style.borderRadius = '6px';
    regInput.value = crop?.RegNumber || '';

    // Type select
    const typeSelect = document.createElement('select');
    typeSelect.style.padding = '8px';
    typeSelect.style.border = '1px solid var(--border)';
    typeSelect.style.borderRadius = '6px';
    typeSelect.innerHTML = '<option value="">(select type)</option>';
    (OPTIONS?.types || []).forEach(t => {
      const typeText = (typeof t === 'string') ? t : (t.StkCrpType || t.StkCrpType || t.type || Object.values(t)[0]);
      const opt = document.createElement('option');
      opt.value = typeText || '';
      opt.textContent = typeText || '';
      typeSelect.appendChild(opt);
    });
    if (crop && crop.Type) {
      Array.from(typeSelect.options).forEach(opt => { if (opt.value === crop.Type) opt.selected = true; });
    }

    // Function input (free-text)
    const funcInput = document.createElement('input');
    funcInput.placeholder = 'Function';
    funcInput.style.padding = '8px';
    funcInput.style.border = '1px solid var(--border)';
    funcInput.style.borderRadius = '6px';
    funcInput.value = crop?.Function || '';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn-ghost';
    removeBtn.textContent = 'Remove';
    removeBtn.addEventListener('click', () => row.remove());

    row.appendChild(cropSelect);
    row.appendChild(regInput);
    row.appendChild(typeSelect);
    row.appendChild(funcInput);
    row.appendChild(removeBtn);

    return row;
  }

  function openModal() {
    (async function(){
      try {
        if (!OPTIONS) {
          const optRes = await fetch('/inventory/product/chemstock_options', { method: 'GET' });
          const optJson = await optRes.json();
          OPTIONS = optJson || {};
        }
      } catch (err) {
        console.error('Failed to load options', err);
        OPTIONS = {};
      }

      // populate selects
      inputActive.innerHTML = '<option value="">(none)</option>';
      console.log('OPTIONS.active_ingredients:', OPTIONS.active_ingredients);
      (OPTIONS.active_ingredients || []).forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.IdChemAct || a.id || a.idUnits || a[0];
        opt.textContent = a.ChemActIngredient || a.name || Object.values(a).join(' ');
        inputActive.appendChild(opt);
      });
      if (CHEMSTOCK.ActiveIngredientId) {
        inputActive.value = CHEMSTOCK.ActiveIngredientId;
      } else if (CHEMSTOCK.ActiveIngredient) {
        Array.from(inputActive.options).forEach(o => { if (o.textContent === CHEMSTOCK.ActiveIngredient) o.selected = true; });
      }

      inputColour.innerHTML = '<option value="">(none)</option>';
      (OPTIONS.colour_codes || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.IdChemCol || c.id || c[0];
        opt.textContent = c.ChemColCode || c.code || Object.values(c).join(' ');
        inputColour.appendChild(opt);
      });
      if (CHEMSTOCK.ColourCodeId) {
        inputColour.value = CHEMSTOCK.ColourCodeId;
      } else if (CHEMSTOCK.ColourCode) {
        Array.from(inputColour.options).forEach(o => { if (o.textContent === CHEMSTOCK.ColourCode) o.selected = true; });
      }

      cropRows.innerHTML = '';
      (CHEMSTOCK.Crops || []).forEach(c => cropRows.appendChild(createCropRow(c)));
      modal.style.display = 'flex';
    })();
  }

  function closeModal() {
    modal.style.display = 'none';
  }

  editBtn.addEventListener('click', openModal);
  cancelBtn.addEventListener('click', closeModal);
  addCropBtn.addEventListener('click', (e) => {
    e.preventDefault();
    cropRows.appendChild(createCropRow({}));
  });

  saveBtn.addEventListener('click', async () => {
    const payload = {
      active_ingredient: inputActive.value || null,
      colour_code: inputColour.value || null,
      crops: []
    };

    for (const r of cropRows.querySelectorAll('.crop-row')) {
      const selects = r.querySelectorAll('select');
      const inputs = r.querySelectorAll('input');
      const cropVal = selects[0]?.value || '';
      const reg = inputs[0]?.value.trim() || '';
      const type = selects[1]?.value || '';
      const func = inputs[1]?.value?.trim() || '';
      if (!cropVal && !reg) continue;
      payload.crops.push({ crop: cropVal, reg_number: reg, type: type, function: func });
    }

    try {
      const res = await request(`/inventory/product/${PRODUCT_STOCK_LINK}/update-chemstock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        alert(data.message || 'Failed to save chemstock');
        return;
      }
      // update UI
      document.getElementById('reg-active').textContent = data.chemstock.ActiveIngredient || '—';
      document.getElementById('reg-colour').textContent = data.chemstock.ColourCode || '—';
      const cropsWrap = document.getElementById('reg-crops-wrap');
      if (data.chemstock.Crops && data.chemstock.Crops.length) {
        let html = '<div class="table-container"><table class="table-compact"><thead><tr><th>Crop</th><th>Reg Number</th><th>Type</th><th>Function</th><th>Withholding Period</th></tr></thead><tbody>';
        data.chemstock.Crops.forEach(c => {
          html += `<tr><td>${c.CropDescription}</td><td>${c.RegNumber}</td><td>${c.Type}</td><td>${c.Function}</td><td>${c.WithholdingPeriod}</td></tr>`;
        });
        html += '</tbody></table></div>';
        cropsWrap.innerHTML = html;
      } else {
        cropsWrap.innerHTML = '<div class="empty-state">No crop registrations on file.</div>';
      }
      closeModal();
    } catch (err) {
      console.error(err);
      alert('Failed to save chemstock: ' + (err.message || err));
    }
  });
});
