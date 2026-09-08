import { db } from '/main_static/offline/db.js?v=60';

const CACHE_MAX_AGE = 7 * 24 * 60 * 60 * 1000;
const userId = String(window.CURRENT_USER_ID || 'unknown');
const readyResolver = window.resolveSprayOfflineReady;

function now() {
    return Date.now();
}

function isFresh(refreshedAt) {
    return Number.isFinite(Number(refreshedAt)) && now() - Number(refreshedAt) < CACHE_MAX_AGE;
}

async function readProjects() {
    const record = await db.spray_projects.get(`user:${userId}`);
    return record || null;
}

async function fetchProjects(force = false) {
    const cached = await readProjects();
    if (!force && cached && isFresh(cached.refreshed_at)) {
        return { projects: cached.projects, refreshed_at: cached.refreshed_at, source: 'cache' };
    }
    if (!navigator.onLine) {
        return cached
            ? { projects: cached.projects, refreshed_at: cached.refreshed_at, source: 'cache' }
            : { projects: [], refreshed_at: null, source: 'offline' };
    }

    let response;
    try {
        response = await fetch('/agri/fetch_projects_for_warehouse', { credentials: 'same-origin' });
    } catch (error) {
        return cached ? { projects: cached.projects, refreshed_at: cached.refreshed_at, source: 'cache' } : { projects: [], refreshed_at: null, source: 'offline' };
    }
    const data = await response.json();
    if (!response.ok || !data.success) {
        return cached ? { projects: cached.projects, refreshed_at: cached.refreshed_at, source: 'cache' } : { projects: [], refreshed_at: null, source: 'offline' };
    }
    const refreshedAt = now();
    await db.spray_projects.put({
        id: `user:${userId}`,
        projects: data.projects || [],
        refreshed_at: refreshedAt
    });
    return { projects: data.projects || [], refreshed_at: refreshedAt, source: 'network' };
}

async function readProducts() {
    const products = await db.spray_product_catalog.toArray();
    if (!products.length) return { products: [], refreshed_at: null };
    return {
        products,
        refreshed_at: Math.min(...products.map(product => Number(product.refreshed_at) || 0))
    };
}

async function refreshProducts(force = false) {
    const cached = await readProducts();
    if (!force && cached.products.length && isFresh(cached.refreshed_at)) {
        return { ...cached, source: 'cache' };
    }
    if (!navigator.onLine) return { ...cached, source: 'cache' };
    let response;
    try {
        response = await fetch('/agri/fetch_products_for_catalog', { credentials: 'same-origin' });
    } catch (error) {
        return { ...cached, source: 'cache' };
    }
    const data = await response.json();
    if (!response.ok || !data.success) return { ...cached, source: 'cache' };
    const refreshedAt = now();
    await db.spray_product_catalog.clear();
    await db.spray_product_catalog.bulkPut((data.products || []).map(product => ({
        ...product,
        stock_id: Number(product.product_link),
        refreshed_at: refreshedAt
    })));
    return { ...(await readProducts()), source: 'network' };
}

async function readMethods() {
    return db.spray_method_catalog.toArray();
}

async function refreshMethods(force = false) {
    const cached = await readMethods();
    const refreshedAt = cached.length ? Math.min(...cached.map(item => Number(item.refreshed_at) || 0)) : null;
    if (!force && cached.length && isFresh(refreshedAt)) return { methods: cached, refreshed_at: refreshedAt, source: 'cache' };
    if (!navigator.onLine) return { methods: cached, refreshed_at: refreshedAt, source: 'cache' };
    let response;
    try {
        response = await fetch('/agri/fetch_methods_for_farms', { credentials: 'same-origin' });
    } catch (error) {
        return { methods: cached, refreshed_at: refreshedAt, source: 'cache' };
    }
    const data = await response.json();
    if (!response.ok || !data.success) return { methods: cached, refreshed_at: refreshedAt, source: 'cache' };
    const records = new Map();
    (data.methods || []).forEach(method => {
        const farmId = Number(method.farm_id);
        if (!records.has(farmId)) records.set(farmId, { farm_id: farmId, methods: [], refreshed_at: now() });
        records.get(farmId).methods.push(method);
    });
    await db.spray_method_catalog.clear();
    await db.spray_method_catalog.bulkPut(Array.from(records.values()));
    return { methods: await readMethods(), refreshed_at: now(), source: 'network' };
}

function productsForProjects(projects) {
    const selectedWarehouses = new Set((projects || []).map(project => String(project.proj_attr_whse_id)));
    const selectedCrops = new Set((projects || []).map(project => String(project.proj_attr_crop_id)));
    return readProducts().then(result => ({
        products: result.products.filter(product =>
            product.warehouse_ids?.some(id => selectedWarehouses.has(String(id))) &&
            product.crop_ids?.some(id => selectedCrops.has(String(id)))
        ),
        refreshed_at: result.refreshed_at,
        source: 'cache'
    }));
}

async function fetchMethods(farmId) {
    const record = await db.spray_method_catalog.get(Number(farmId));
    return record || { methods: [], refreshed_at: null, source: 'cache' };
}

async function initializeData(force = false) {
    const projectsResult = await fetchProjects(force);
    const productsResult = await refreshProducts(force);
    const methodsResult = await refreshMethods(force);
    return { projects: projectsResult.projects, products: productsResult, methods: methodsResult };
}

function localRecommendationId() {
    const uuid = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    return `local-${uuid}`;
}

async function saveLocalRecommendation(payload, status, response = null, error = null) {
    const id = response?.id || localRecommendationId();
    const record = {
        user_id: userId,
        id,
        local_id: response?.id ? null : id,
        status,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        spray_no: response?.spray_no || `Pending ${id.slice(-8)}`,
        spray_date: payload.spray_date || null,
        spray_week: payload.spray_week || null,
        description: payload.spray_description || '',
        warehouse_id: payload.warehouse_id || null,
        project_ids: (payload.projects || []).map(project => project.project_id),
        detail: payload,
        error: error ? String(error) : null,
        backend: response || null
    };
    await db.spray_recommendations.put(record);
    return record;
}

async function postRecommendation(payload) {
    const response = await fetch('/agri/spray-recommendation/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        const error = new Error(data.message || 'Failed to save recommendation');
        error.status = response.status;
        throw error;
    }

    let finalStatus = 'RECOMMENDED';
    if (payload.create_execution_immediately) {
        const executionResponse = await fetch('/agri/execution/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ recommendation_ids: [data.id], execution_date: payload.spray_date })
        });
        const executionData = await executionResponse.json();
        if (!executionResponse.ok || !executionData.success) throw new Error(executionData.message || 'Failed to create execution');
        finalStatus = 'SCHEDULED';
        data.execution_id = executionData.execution_id;
    }
    await saveLocalRecommendation(payload, finalStatus, data);
    return { queued: false, data };
}

async function submitOrQueue(payload) {
    if (!navigator.onLine) {
        const record = await saveLocalRecommendation(payload, 'WAITING_TO_SYNC');
        return { queued: true, record };
    }
    try {
        return await postRecommendation(payload);
    } catch (error) {
        if (!navigator.onLine || error instanceof TypeError || error.status === 503) {
            const record = await saveLocalRecommendation(payload, 'WAITING_TO_SYNC', null, error);
            return { queued: true, record };
        }
        throw error;
    }
}

async function syncPending() {
    if (!navigator.onLine) return [];
    const pending = await db.spray_recommendations.where('status').equals('WAITING_TO_SYNC').toArray();
    const synced = [];
    for (const record of pending) {
        try {
            const result = await postRecommendation(record.detail);
            await db.spray_recommendations.delete([userId, record.id]);
            synced.push(result.data);
        } catch (error) {
            const transient = !navigator.onLine || error instanceof TypeError || error.status === 503;
            await db.spray_recommendations.update([userId, record.id], {
                status: transient ? 'WAITING_TO_SYNC' : 'FAILED_TO_SYNC',
                error: String(error),
                updated_at: new Date().toISOString()
            });
        }
    }
    return synced;
}

async function readRecommendations() {
    return db.spray_recommendations.where('user_id').equals(userId).toArray();
}

async function readRecommendation(id) {
    return db.spray_recommendations.get([userId, Number(id)]);
}

async function fetchInstructionDetails(ids) {
    const response = await fetch('/agri/spray/instructions/details', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ spray_ids: ids.map(Number) })
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.message || 'Failed to refresh spray instructions');
    }
    return data.items || [];
}

async function refreshInstructions(ids, force = true) {
    if (!navigator.onLine) {
        throw new Error('You are offline. Connect before refreshing the spray instruction.');
    }
    const uniqueIds = [...new Set(ids.map(Number).filter(Number.isFinite))];
    if (!uniqueIds.length) return [];
    if (!force) {
        const cached = await Promise.all(uniqueIds.map(readRecommendation));
        if (cached.every(record => record?.detail)) return cached;
    }
    const details = await fetchInstructionDetails(uniqueIds);
    const detailsById = new Map(details.map(item => [Number(item.id), item]));
    const missingIds = uniqueIds.filter(id => !detailsById.has(id));
    if (missingIds.length) {
        throw new Error(`The server did not return spray instruction details for: ${missingIds.join(', ')}`);
    }
    const refreshedAt = now();
    const updated = [];
    for (const id of uniqueIds) {
        const item = detailsById.get(id);
        const record = await readRecommendation(id);
        const next = {
            ...(record || { user_id: userId, id }),
            id, user_id: userId, refreshed_at: refreshedAt,
            modified_at: item.detail.header.modified_at || record?.modified_at || null,
            detail: item.detail
        };
        await db.spray_recommendations.put(next);
        updated.push(next);
    }
    return updated;
}

async function refreshInstruction(id, force = true) {
    const records = await refreshInstructions([id], force);
    return records[0] || null;
}

async function refreshRecommendations() {
    if (!navigator.onLine) {
        throw new Error('You are offline. Connect before refreshing recommendations.');
    }

    const response = await fetch('/agri/spray-recommendations', { credentials: 'same-origin' });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.message || 'Failed to refresh recommendations');
    }

    const existing = await readRecommendations();
    const localPending = existing.filter(record => ['WAITING_TO_SYNC', 'FAILED_TO_SYNC'].includes(record.status));
    const refreshedAt = now();
    const existingById = new Map(existing.map(record => [Number(record.id), record]));
    const records = (data.items || []).map(item => ({
        ...(existingById.get(Number(item.id)) || {}),
        user_id: userId,
        id: item.id,
        local_id: null,
        status: item.status || 'RECOMMENDED',
        created_at: item.start_date || item.end_date || new Date().toISOString(),
        updated_at: refreshedAt,
        refreshed_at: refreshedAt,
        spray_no: item.spray_no,
        spray_date: item.start_date || null,
        spray_week: item.week,
        description: item.description,
        warehouse_id: item.warehouse_id,
        warehouse_name: item.warehouse_name,
        execution_id: item.execution_id,
        block_no: item.block_no,
        farm_name: item.farm_name,
        finalised: item.finalised,
        modified_at: item.modified_at || null,
        backend: item
    }));

    const detailIds = records
        .filter(record => {
            const cached = existingById.get(Number(record.id));
            return !cached?.detail || cached.modified_at !== record.modified_at;
        })
        .map(record => Number(record.id));

    await db.spray_recommendations.bulkPut(records);
    if (detailIds.length) {
        await refreshInstructions(detailIds);
    }

    const serverIds = new Set(records.map(record => Number(record.id)));
    const staleIds = existing
        .filter(record => !['WAITING_TO_SYNC', 'FAILED_TO_SYNC'].includes(record.status))
        .filter(record => !serverIds.has(Number(record.id)))
        .map(record => [userId, record.id]);
    if (staleIds.length) {
        await db.spray_recommendations.bulkDelete(staleIds);
    }

    const hydrated = await Promise.all(records.map(record => readRecommendation(record.id)));
    if (hydrated.some(record => !record?.detail)) {
        throw new Error('One or more spray instructions could not be cached.');
    }
    await db.meta.put({ key: `spray_recommendations_refreshed:${userId}`, refreshed_at: refreshedAt });
    return [...hydrated, ...localPending];
}

async function recommendationRefreshTime() {
    const record = await db.meta.get(`spray_recommendations_refreshed:${userId}`);
    return record?.refreshed_at || null;
}

async function markRecommendationsScheduled(ids, executionId) {
    for (const id of ids) {
        await db.spray_recommendations.update([userId, Number(id)], {
            execution_id: executionId,
            status: 'SCHEDULED',
            updated_at: now()
        });
    }
}

async function lastRefreshes(projects = []) {
    const projectCache = await readProjects();
    const productCache = await readProducts();
    const methods = await readMethods();
    return {
        projects: projectCache?.refreshed_at || null,
        products: productCache.refreshed_at,
        methods: methods.length ? Math.min(...methods.map(item => item.refreshed_at)) : null
    };
}

const api = {
    fetchProjects,
    refreshProducts,
    refreshMethods,
    fetchMethods,
    productsForProjects,
    initializeData,
    submitOrQueue,
    syncPending,
    readRecommendations,
    readRecommendation,
    fetchInstructionDetails,
    refreshInstructions,
    refreshRecommendations,
    refreshInstruction,
    recommendationRefreshTime,
    markRecommendationsScheduled,
    lastRefreshes,
    isFresh,
    cacheMaxAge: CACHE_MAX_AGE
};
window.SprayOffline = api;
if (readyResolver) readyResolver(api);
window.dispatchEvent(new CustomEvent('spray-offline-ready'));
function syncPendingRecommendations() {
    return syncPending()
        .then(records => {
            if (records.length) {
                window.dispatchEvent(new CustomEvent('spray-recommendations-synced', { detail: records }));
            }
            return records;
        })
        .catch(error => {
            console.error('Spray sync failed', error);
            return [];
        });
}
window.addEventListener('online', syncPendingRecommendations);
if (navigator.onLine) syncPendingRecommendations();
