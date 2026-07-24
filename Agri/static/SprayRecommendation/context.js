
/* ================== CONTEXT SHEET (CLIENT-SIDE FILTERING & CHIP UI) ================== */
// Replace previous context fetch + render logic with client-side filtering and Gmail-like chips.
// Backend now returns a dataset (last year / warehouse ) and a simple filters object.

let contextState = {
    items: [],
    filteredItems: [],
    activeFilters: {
        projects: new Set(),
        products: new Set(),
        active_ingredients: new Set(),
        types: new Set(),
        ranges: new Set() // e.g. "last_year", "last_6_months"
    },
    expanded: false,
    monthsBack: 12,
};

const contextSheet = document.getElementById('context-sheet');
const contextHandle = document.getElementById('context-handle');
const contextClose = document.getElementById('context-close');
const contextBody = document.getElementById('context-body');

contextHandle.addEventListener('click', () => {
    contextState.expanded = !contextState.expanded;
    contextSheet.classList.toggle('open', contextState.expanded);
    contextHandle.setAttribute('aria-expanded', contextState.expanded);
});

contextClose.addEventListener('click', () => {
    contextState.expanded = false;
    contextSheet.classList.remove('open');
    contextHandle.setAttribute('aria-expanded', false);
});

function normalizeLookupItems(list) {
    if (!list) return [];

    if (Array.isArray(list)) {
        return list.map(item => {
            if (item && typeof item === 'object') {
                const id = item.id ?? item.value ?? item.ProjectId ?? item.StockId ?? item.active_ingredient_id ?? item.crop_id ?? item;
                const name = item.name ?? item.label ?? item.ProjectName ?? item.StockDescription ?? item.ChemActIngredient ?? item.CropDescription ?? String(item);
                return { id: String(id), name: String(name) };
            }
            return { id: String(item), name: String(item) };
        });
    }

    if (typeof list === 'object') {
        return Object.entries(list).map(([key, value]) => ({ id: String(key), name: String(value) }));
    }

    return [{ id: String(list), name: String(list) }];
}

function getFilterValueFromItem(item, category) {
    switch (category) {
        case 'projects':
            return String(item.project_id ?? item.ProjectId ?? item.ProjectLink ?? '');
        case 'products':
            return String(item.stock_id ?? item.StockId ?? item.SprayLineStkId ?? '');
        case 'active_ingredients':
            return String(item.active_ingredient_id ?? item.IdChemAct ?? item.active_ingredient ?? item.ChemActIngredient ?? '');
        case 'types':
            return String(item.type ?? item.StkCrpType ?? '');
        default:
            return String('');
    }
}

// Render filter chips from dataset lookups (safe no-op if container missing)
function renderFilterChipsFromDataset(lookups) {
    const container = document.getElementById('context-active-chips');
    if (!container) return;
    container.innerHTML = '';

    const categories = [
        { key: 'projects', label: 'Projects' },
        { key: 'products', label: 'Products' },
        { key: 'active_ingredients', label: 'Active Ingredients' },
        { key: 'types', label: 'Types' }
    ];

    let any = false;
    categories.forEach(cat => {
        const items = normalizeLookupItems(lookups[cat.key]);
        items.forEach(item => {
            any = true;

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'context-chip';
            btn.dataset.filterCategory = cat.key;
            btn.dataset.filterValue = item.id;
            btn.textContent = item.name;

            if (contextState.activeFilters[cat.key]?.has(item.id)) {
                btn.classList.add('active');
            }

            btn.addEventListener('click', function () {
                const category = this.dataset.filterCategory;
                const value = this.dataset.filterValue;
                const set = contextState.activeFilters[category] || new Set();
                if (set.has(value)) {
                    set.delete(value);
                    this.classList.remove('active');
                } else {
                    set.add(value);
                    this.classList.add('active');
                }
                contextState.activeFilters[category] = set;
                applyContextFilters();
            });

            container.appendChild(btn);
        });
    });

    if (!any) {
        container.innerHTML = '<span class="context-chip">No filters</span>';
    }
}

// Apply active filters to the context dataset and re-render
function applyContextFilters() {
    // We receive grouped items from the backend (by date). For filtering
    // flatten entries into `flatItems`, apply filters, then regroup by date
    if (!contextState.flatItems) return;

    const flat = contextState.flatItems.slice();

    const filteredFlat = flat.filter(it => {
        // projects
        const pset = contextState.activeFilters.projects;
        console.log('Filtering item', it, 'against projects', pset);
        if (pset && pset.size) {
            const projId = getFilterValueFromItem(it, 'projects');
            if (!projId || !pset.has(projId)) return false;
        }

        // products
        const prset = contextState.activeFilters.products;
        if (prset && prset.size) {
            const stock = getFilterValueFromItem(it, 'products');
            if (!stock || !prset.has(stock)) return false;
        }

        // active_ingredients
        const aiset = contextState.activeFilters.active_ingredients;
        if (aiset && aiset.size) {
            const ai = getFilterValueFromItem(it, 'active_ingredients');
            if (!ai || !aiset.has(ai)) return false;
        }

        // types
        const tset = contextState.activeFilters.types;
        if (tset && tset.size) {
            const ty = getFilterValueFromItem(it, 'types');
            if (!ty || !tset.has(ty)) return false;
        }

        return true;
    });

    // regroup by _date into array of {date, entries}
    const grouped = {};
    filteredFlat.forEach(it => {
        grouped[it._date] = grouped[it._date] || [];
        grouped[it._date].push(it);
    });

    const groupedArr = Object.keys(grouped).sort((a,b) => b.localeCompare(a)).map(d => ({ date: d, entries: grouped[d] }));
    contextState.filteredItems = groupedArr;

    renderContextStats();
    renderContextTimeline();
}

// Render summary stat cards for the context sheet
function renderContextStats() {
    const container = document.getElementById('context-stats');
    if (!container) return;

    // contextState.filteredItems is grouped by date; compute totals from flattened view
    const groups = contextState.filteredItems || [];
    const flat = [];
    groups.forEach(g => (g.entries || []).forEach(e => flat.push(e)));

    const total = flat.length;
    const projects = new Set();
    const products = new Set();
    flat.forEach(it => {
        if (it.project_id || it.ProjectId) projects.add(String(it.project_id || it.ProjectId));
        if (it.stock_id || it.StockId) products.add(String(it.stock_id || it.StockId));
    });

    container.innerHTML = `
        <div class="context-stat"><strong>${total}</strong>Records</div>
        <div class="context-stat"><strong>${projects.size}</strong>Projects</div>
        <div class="context-stat"><strong>${products.size}</strong>Products</div>
    `;
}

// Render the timeline list of context items
function renderContextTimeline() {
    const container = document.getElementById('context-timeline');
    if (!container) return;

    const groups = contextState.filteredItems || [];
    if (!groups.length) {
        container.innerHTML = '<div class="context-empty">No history for the selected filters.</div>';
        return;
    }

    container.innerHTML = '';

    // each group is {date, entries: [...]}
    groups.forEach(group => {
        const header = document.createElement('div');
        header.style.fontWeight = '700';
        header.style.margin = '8px 0';
        header.textContent = group.date;
        container.appendChild(header);

        (group.entries || []).forEach(it => {
            const project = it.project_name || it.ProjectName || '';
            const desc = it.stock_description || it.StockDescription || '';
            const qtyRec = (it.qty_recommended != null) ? it.qty_recommended : (it.QtyRecommended != null ? it.QtyRecommended : '-');
            const qtyIss = (it.qty_issued != null) ? it.qty_issued : (it.QtyIssued != null ? it.QtyIssued : '-');

            const card = document.createElement('details');
            card.className = 'context-card';

            const summary = document.createElement('summary');
            summary.style.display = 'flex';
            summary.style.justifyContent = 'space-between';
            summary.style.alignItems = 'center';

            const left = document.createElement('div');
            left.style.minWidth = '0';
            left.innerHTML = `<div class="context-title">${project}</div><div class="context-meta">${desc}</div>`;

            const right = document.createElement('div');
            right.style.textAlign = 'right';
            right.innerHTML = `<div class="context-date">${group.date}</div><div class="context-meta">Rec: ${qtyRec} • Iss: ${qtyIss}</div>`;

            summary.appendChild(left);
            summary.appendChild(right);
            card.appendChild(summary);

            const expanded = document.createElement('div');
            expanded.className = 'context-expanded';
            const colLeft = document.createElement('div');
            colLeft.className = 'context-expanded-col';
            colLeft.innerHTML = '<strong>Active Ingredient</strong>';
            const colRight = document.createElement('div');
            colRight.className = 'context-expanded-col';
            colRight.innerHTML = '<strong>Details</strong>';

            const prodRow = document.createElement('div');
            prodRow.className = 'context-line-item';
            prodRow.innerHTML = `<div class="context-line-name">${it.active_ingredient || ''}</div><div class="context-line-qty">Rec: ${qtyRec} ${it.uom || ''}</div>`;
            colLeft.appendChild(prodRow);

            const detailsRow = document.createElement('div');
            detailsRow.className = 'context-line-item';
            detailsRow.innerHTML = `<div class="context-line-name">Type: ${it.type || it.StkCrpType || ''}</div><div class="context-line-qty">Crop: ${it.crop_description || it.CropDescription || ''}</div>`;
            colRight.appendChild(detailsRow);

            expanded.appendChild(colLeft);
            expanded.appendChild(colRight);
            card.appendChild(expanded);

            container.appendChild(card);
        });
    });
}

async function updateContextDataset() {
    // use jQuery to read Select2 value reliably
    const warehouseId = $('#warehouse_id').val();
    const rangeMonths = $('#filter-range').val() || '6';
    if (!warehouseId || String(warehouseId).trim() === '') {
        document.getElementById('context-timeline').innerHTML = '<div class="context-empty">Select a warehouse to view recent spray context.</div>';
        document.getElementById('context-stats').innerHTML = '';
        return;
    }
    const params = new URLSearchParams();
    params.set('warehouse_id', warehouseId);
    if (rangeMonths !== '0') {
        const months = parseInt(rangeMonths, 10) || 6;
        const startDate = new Date();
        startDate.setMonth(startDate.getMonth() - months);
        params.set('start_date', startDate.toISOString().slice(0, 10));
    }
    const res = await fetch(`/agri/spray-recommendation/context?${params.toString()}`);
    const data = await res.json();
    contextState.items = data.items || [];
    contextState.lookups = data.lookups || {};
    contextState.suggestions = data.suggestions || {};

    // flatten entries with date for filtering
    const flat = [];
    contextState.items.forEach(g => (g.entries || []).forEach(e => flat.push(Object.assign({ _date: g.date }, e))));
    contextState.flatItems = flat;

    // initial grouped filtered = backend grouping
    contextState.filteredItems = contextState.items.slice();
    renderFilterChipsFromDataset(data.lookups || {});
    renderContextStats();
    renderContextTimeline();
}

// ensure context updates when warehouse/projects change
$('#warehouse_id').on('change', function() {
    updateContextDataset(); // <- ensure history refresh
});