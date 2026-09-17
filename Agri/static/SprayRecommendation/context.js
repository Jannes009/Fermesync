let contextState = {
    items: [],
    expanded: false,
    availableWeeks: [],
    startWeek: null,
    endWeek: null,
    projectKey: '',
    loading: false
};

const contextSheet = document.getElementById('context-sheet');
const contextHandle = document.getElementById('context-handle');
const contextClose = document.getElementById('context-close');

function escapeContextText(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[character]));
}

function populateWeekFilters(weeks = contextState.availableWeeks) {
    const startSelect = document.getElementById('context-start-week');
    const endSelect = document.getElementById('context-end-week');
    if (!startSelect || !endSelect) return;

    [startSelect, endSelect].forEach(select => {
        select.innerHTML = '';
        weeks.forEach(week => select.appendChild(new Option(week, week)));
    });
    if (weeks.length) {
        contextState.startWeek = weeks.includes(contextState.startWeek) ? contextState.startWeek : weeks[0];
        contextState.endWeek = weeks.includes(contextState.endWeek) ? contextState.endWeek : weeks[weeks.length - 1];
        startSelect.value = contextState.startWeek;
        endSelect.value = contextState.endWeek;
    }
}

function selectedProjectIds() {
    return ($('#project_ids').val() || []).map(value => String(value)).filter(Boolean);
}

function renderContextStats() {
    const container = document.getElementById('context-stats');
    if (!container) return;
    const products = new Set(contextState.items.map(item => String(item.stock_id)));
    const ingredients = new Set(contextState.items.map(item => item.active_ingredient || 'Unspecified'));
    const total = contextState.items.reduce((sum, item) => sum + Number(item.total_qty || 0), 0);
    container.innerHTML = `
        <div class="context-stat"><strong>${ingredients.size}</strong>Active ingredients</div>
        <div class="context-stat"><strong>${products.size}</strong>Products</div>
        <div class="context-stat"><strong>${contextState.items.length}</strong>Weekly records</div>
    `;
}

function renderContextTimeline() {
    const container = document.getElementById('context-timeline');
    if (!container) return;
    if (contextState.loading) {
        container.innerHTML = '<div class="context-empty">Loading product history...</div>';
        return;
    }
    if (!contextState.items.length) {
        container.innerHTML = '<div class="context-empty">No product history for the selected projects and weeks.</div>';
        return;
    }

    const ingredients = new Map();
    contextState.items.forEach(item => {
        const ingredientKey = item.active_ingredient || '__unspecified__';
        if (!ingredients.has(ingredientKey)) {
            ingredients.set(ingredientKey, {
                name: item.active_ingredient || 'Unspecified active ingredient',
                products: new Map()
            });
        }
        const ingredient = ingredients.get(ingredientKey);
        const productKey = String(item.stock_id);
        if (!ingredient.products.has(productKey)) {
            ingredient.products.set(productKey, {
                    name: item.stock_description || 'Unnamed product',
                    uom: item.uom || '',
                    total: 0,
                    records: []
                });
        }
        const product = ingredient.products.get(productKey);
        product.total += Number(item.total_qty || 0);
        product.records.push(item);
    });

    container.innerHTML = '';
    ingredients.forEach(ingredient => {
        const section = document.createElement('section');
        section.className = 'context-ingredient-group';
        section.innerHTML = `<h4 class="context-ingredient-title">${escapeContextText(ingredient.name)}</h4>`;

        ingredient.products.forEach(product => {
            product.records.sort((left, right) => String(left.spray_week).localeCompare(String(right.spray_week)));
            const card = document.createElement('details');
            card.className = 'context-card';
            card.innerHTML = `
                <summary>
                    <div class="context-card-header">
                        <div class="context-title">${escapeContextText(product.name)}</div>
                        <div class="context-meta">${product.records.length} week${product.records.length === 1 ? '' : 's'}</div>
                    </div>
                    <div class="context-product-total">${product.total.toFixed(2)} ${escapeContextText(product.uom)}</div>
                </summary>
                <div class="context-expanded"></div>
            `;
            const details = card.querySelector('.context-expanded');
            product.records.forEach(record => {
                const row = document.createElement('div');
                row.className = 'context-line-item';
                row.innerHTML = `
                    <div>
                        <strong>${escapeContextText(record.spray_week)}</strong>
                        <div class="context-meta">${escapeContextText(record.project_name || `Project ${record.project_id}`)}</div>
                        <div class="context-meta">${escapeContextText(record.description || 'No description')}</div>
                    </div>
                    <div class="context-line-qty">${Number(record.total_qty || 0).toFixed(2)} ${escapeContextText(record.uom || '')}</div>
                `;
                details.appendChild(row);
            });
            section.appendChild(card);
        });
        container.appendChild(section);
    });
}

async function updateContextDataset() {
    const projectIds = selectedProjectIds();
    const projectKey = projectIds.join(',');
    if (!projectIds.length) {
        contextState.items = [];
        contextState.availableWeeks = [];
        contextState.startWeek = null;
        contextState.endWeek = null;
        contextState.projectKey = '';
        populateWeekFilters();
        renderContextStats();
        renderContextTimeline();
        return;
    }
    if (!contextState.expanded) return;
    if (contextState.projectKey !== projectKey) {
        contextState.projectKey = projectKey;
        contextState.availableWeeks = [];
        contextState.startWeek = null;
        contextState.endWeek = null;
        populateWeekFilters();
    }

    contextState.loading = true;
    renderContextTimeline();
    const params = new URLSearchParams({
        ...(contextState.startWeek ? { start_week: contextState.startWeek } : {}),
        ...(contextState.endWeek ? { end_week: contextState.endWeek } : {})
    });
    projectIds.forEach(projectId => params.append('project_id', projectId));

    try {
        const response = await request(`/agri/spray-recommendation/context?${params.toString()}`);
        const data = await response.json();
        if (!data.success) throw new Error(data.message || 'Unable to fetch product history');
        contextState.availableWeeks = data.available_weeks || [];
        populateWeekFilters();
        contextState.items = data.items || [];
    } catch (error) {
        contextState.items = [];
        const container = document.getElementById('context-timeline');
        if (container) container.innerHTML = `<div class="context-empty">${escapeContextText(error.message)}</div>`;
    } finally {
        contextState.loading = false;
        renderContextStats();
        renderContextTimeline();
    }
}

contextHandle?.addEventListener('click', () => {
    contextState.expanded = !contextState.expanded;
    contextSheet.classList.toggle('open', contextState.expanded);
    contextHandle.setAttribute('aria-expanded', String(contextState.expanded));
    if (contextState.expanded) updateContextDataset();
});

contextClose?.addEventListener('click', () => {
    contextState.expanded = false;
    contextSheet.classList.remove('open');
    contextHandle.setAttribute('aria-expanded', 'false');
});

populateWeekFilters();
['context-start-week', 'context-end-week'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', event => {
        const value = event.target.value;
        if (id === 'context-start-week') contextState.startWeek = value;
        if (id === 'context-end-week') contextState.endWeek = value;
        if (contextState.startWeek > contextState.endWeek) {
            if (id === 'context-start-week') contextState.endWeek = contextState.startWeek;
            else contextState.startWeek = contextState.endWeek;
            populateWeekFilters(contextState.availableWeeks);
        }
        updateContextDataset();
    });
});

renderContextStats();
renderContextTimeline();
