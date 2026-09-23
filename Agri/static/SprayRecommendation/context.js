let contextState = {
    items: [],
    expanded: false,
    availableWeeks: [],
    startWeek: null,
    endWeek: null,
    projectKey: '',
    loading: false,
    error: null,
    loaded: false,
    ingredientView: null,
    hadSelectedProducts: false
};

const contextSheet = document.getElementById('context-sheet');
const contextHandle = document.getElementById('context-handle');
const contextClose = document.getElementById('context-close');
const contextSearch = document.getElementById('context-search');
let contextDrag = null;
let suppressContextClick = false;

function setContextHeight(height) {
    const minHeight = 52;
    const maxHeight = Math.min(window.innerHeight * 0.92, 900);
    const clampedHeight = Math.max(minHeight, Math.min(maxHeight, height));
    contextSheet.style.height = `${clampedHeight}px`;
    return clampedHeight;
}

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

function selectedActiveIngredients() {
    const ingredients = new Set();
    document.querySelectorAll('.product-select').forEach(select => {
        const option = select.selectedOptions[0];
        if (!option || !select.value) return;
        const ingredient = option.textContent.split(' - ', 1)[0].trim();
        if (ingredient) ingredients.add(ingredient);
    });
    return ingredients;
}

function syncIngredientViewDefault() {
    const hasSelectedProducts = selectedActiveIngredients().size > 0;
    if (contextState.ingredientView === null || contextState.hadSelectedProducts !== hasSelectedProducts) {
        contextState.ingredientView = hasSelectedProducts ? 'selected' : 'all';
        const radio = document.querySelector(`input[name="context-ingredient-view"][value="${contextState.ingredientView}"]`);
        if (radio) radio.checked = true;
    }
    contextState.hadSelectedProducts = hasSelectedProducts;
}

function contextSearchTerm() {
    return String(contextSearch?.value || '').trim().toLocaleLowerCase();
}

function contextRetryMarkup() {
    return '<button type="button" class="btn ghost context-retry" id="context-retry">Retry</button>';
}

function renderContextTimeline() {
    const container = document.getElementById('context-timeline');
    if (!container) return;
    if (contextState.loading) {
        container.innerHTML = '<div class="context-empty">Loading product history...</div>';
        return;
    }
    if (contextState.error) {
        container.innerHTML = `<div class="context-empty context-error" role="alert">Unable to load product history.<br>${escapeContextText(contextState.error)}<br>${contextRetryMarkup()}</div>`;
        return;
    }
    if (!contextState.items.length) {
        container.innerHTML = `<div class="context-empty">No product history for the selected projects and weeks.<br>${contextRetryMarkup()}</div>`;
        return;
    }

    syncIngredientViewDefault();
    const selectedIngredients = selectedActiveIngredients();
    const showSelectedOnly = contextState.ingredientView === 'selected';
    const searchTerm = contextSearchTerm();
    const ingredients = new Map();
    console.log(contextState.items, selectedIngredients, showSelectedOnly, searchTerm);
    contextState.items.forEach(item => {
        const ingredientKey = item.active_ingredient || '__unspecified__';
        if (showSelectedOnly && !selectedIngredients.has(item.active_ingredient || '')) return;
        const ingredientName = item.active_ingredient || 'Unspecified active ingredient';
        const productName = item.stock_description || 'Unnamed product';
        if (searchTerm && !`${ingredientName} ${productName}`.toLocaleLowerCase().includes(searchTerm)) return;
        if (!ingredients.has(ingredientKey)) {
            ingredients.set(ingredientKey, {
                name: ingredientName,
                products: new Map()
            });
        }
        const ingredient = ingredients.get(ingredientKey);
        const productKey = String(item.stock_id);
        if (!ingredient.products.has(productKey)) {
            ingredient.products.set(productKey, {
                    name: productName,
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
    if (!ingredients.size) {
        container.innerHTML = searchTerm
            ? '<div class="context-empty">No history matches your search.</div>'
            : showSelectedOnly
                ? '<div class="context-empty">Select a product to view its active ingredient history.</div>'
                : '<div class="context-empty">No product history for the selected projects and weeks.</div>';
        return;
    }
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
        contextState.error = null;
        contextState.loaded = false;
        populateWeekFilters();
        renderContextTimeline();
        return;
    }
    if (!contextState.expanded) return;
    if (contextState.projectKey !== projectKey) {
        contextState.projectKey = projectKey;
        contextState.loaded = false;
        contextState.availableWeeks = [];
        contextState.startWeek = null;
        contextState.endWeek = null;
        contextState.error = null;
        populateWeekFilters();
    }
    if (contextState.loaded) {
        renderContextTimeline();
        return;
    }

    contextState.loading = true;
    contextState.error = null;
    renderContextTimeline();
    const params = new URLSearchParams({
        ...(contextState.startWeek ? { start_week: contextState.startWeek } : {}),
        ...(contextState.endWeek ? { end_week: contextState.endWeek } : {})
    });
    projectIds.forEach(projectId => params.append('project_id', projectId));

    try {
        const response = await request(`/agri/spray-recommendation/context?${params.toString()}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || `Unable to fetch product history (HTTP ${response.status})`);
        }
        contextState.availableWeeks = data.available_weeks || [];
        populateWeekFilters();
        contextState.items = data.items || [];
        contextState.error = null;
        contextState.loaded = true;
    } catch (error) {
        contextState.items = [];
        contextState.error = error instanceof Error ? error.message : String(error);
        contextState.loaded = false;
    } finally {
        contextState.loading = false;
        renderContextTimeline();
    }
}

contextHandle?.addEventListener('click', () => {
    if (suppressContextClick) {
        suppressContextClick = false;
        return;
    }
    contextSheet.style.height = '';
    contextState.expanded = !contextState.expanded;
    contextSheet.classList.toggle('open', contextState.expanded);
    contextHandle.setAttribute('aria-expanded', String(contextState.expanded));
    console.log(contextState.expanded, contextState.loaded);
    if (contextState.expanded) updateContextDataset();
});

contextHandle?.addEventListener('pointerdown', event => {
    contextDrag = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startHeight: contextSheet.getBoundingClientRect().height,
        moved: false
    };
    contextSheet.classList.add('dragging');
    contextHandle.setPointerCapture?.(event.pointerId);
});

contextHandle?.addEventListener('pointermove', event => {
    if (!contextDrag || event.pointerId !== contextDrag.pointerId) return;
    const delta = event.clientY - contextDrag.startY;
    if (Math.abs(delta) < 4) return;
    contextDrag.moved = true;
    setContextHeight(contextDrag.startHeight - delta);
});

function finishContextDrag() {
    if (!contextDrag) return;
    if (contextDrag.moved) {
        const height = contextSheet.getBoundingClientRect().height;
        const open = height > 52;
        contextState.expanded = open;
        contextSheet.classList.toggle('open', open);
        contextHandle.setAttribute('aria-expanded', String(open));
        if (open) updateContextDataset();
        suppressContextClick = true;
    }
    contextSheet.classList.remove('dragging');
    contextDrag = null;
}

contextHandle?.addEventListener('pointerup', finishContextDrag);
contextHandle?.addEventListener('pointercancel', finishContextDrag);

contextClose?.addEventListener('click', () => {
    contextState.expanded = false;
    contextSheet.classList.remove('open');
    contextSheet.classList.remove('dragging');
    contextHandle.setAttribute('aria-expanded', 'false');
    contextSheet.style.height = '';
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
        contextState.loaded = false;
        updateContextDataset();
    });
});

document.querySelectorAll('input[name="context-ingredient-view"]').forEach(radio => {
    radio.addEventListener('change', event => {
        contextState.ingredientView = event.target.value;
        renderContextTimeline();
    });
});

contextSearch?.addEventListener('input', renderContextTimeline);

document.addEventListener('click', event => {
    if (!event.target.closest('#context-retry')) return;
    contextState.loaded = false;
    updateContextDataset();
});

$(document).on('change', '.product-select', () => {
    syncIngredientViewDefault();
    renderContextTimeline();
});

document.addEventListener('spray-draft-restored', () => {
    contextState.projectKey = '';
    contextState.loaded = false;
    contextState.availableWeeks = [];
    contextState.startWeek = null;
    contextState.endWeek = null;
    updateContextDataset();
});

renderContextTimeline();
