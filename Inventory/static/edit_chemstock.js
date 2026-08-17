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

      // enhance styling (small but visible) and add 'add active ingredient' button next to active select
      inputActive.style.minWidth = '240px';
      inputActive.style.marginRight = '8px';

      // create add button if not present
      if (!document.getElementById('add-active-btn')) {
        const addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.id = 'add-active-btn';
        addBtn.className = 'btn-primary';
        addBtn.textContent = 'Add';
        addBtn.style.margin = '4px';
        addBtn.style.padding = '8px 10px';
        addBtn.addEventListener('click', openAddActiveModal);
        inputActive.parentNode.appendChild(addBtn);
      }
    })();
  }

  function closeModal() {
    modal.style.display = 'none';
  }

  // Small modal for adding an active ingredient
  function openAddActiveModal() {
    // If modal exists, show it
    let small = document.getElementById('add-active-modal');
    if (!small) {
      small = document.createElement('div');
      small.id = 'add-active-modal';
      small.style.position = 'fixed';
      small.style.right = '20px';
      small.style.top = '120px';
      small.style.zIndex = 11000;
      small.style.background = '#fff';
      small.style.border = '1px solid rgba(0,0,0,0.08)';
      small.style.borderRadius = '8px';
      small.style.boxShadow = '0 6px 20px rgba(0,0,0,0.12)';
      small.style.padding = '12px';
      small.innerHTML = `
        <div style="font-weight:700;margin-bottom:8px;">New Active Ingredient</div>
        <input id="new-active-name" placeholder="e.g. Glyphosate" style="padding:8px;border:1px solid #ddd;border-radius:6px;width:220px;margin-bottom:8px;" />
        <div style="display:flex;gap:8px;justify-content:flex-end;">
          <button id="cancel-new-active" class="btn-ghost" style="padding:6px 10px;">Cancel</button>
          <button id="save-new-active" class="btn-primary" style="padding:6px 10px;">Save</button>
        </div>
      `;
      document.body.appendChild(small);
      document.getElementById('cancel-new-active').addEventListener('click', () => small.remove());
      document.getElementById('save-new-active').addEventListener('click', async () => {
        const name = document.getElementById('new-active-name').value.trim();
        if (!name) return alert('Please enter a name');
        try {
          const res = await request('/inventory/product/chemstock/add-active-ingredient', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name })
          });
          const data = await res.json();
          if (!res.ok || !data.success) {
            return alert(data.message || 'Failed to add');
          }
          // Refresh options and select the new one
          const opt = document.createElement('option');
          opt.value = data.id;
          opt.textContent = data.name;
          inputActive.appendChild(opt);
          inputActive.value = data.id;
          // remove small modal
          small.remove();
        } catch (err) {
          console.error(err);
          alert('Failed to create active ingredient');
        }
      });
    }
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
