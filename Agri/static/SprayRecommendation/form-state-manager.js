/**
 * Form State Manager
 * 
 * Saves and restores the spray recommendation form state using localStorage.
 * Handles async loading order and provides user recovery prompts for stale drafts.
 * 
 * Key features:
 * - User-specific draft storage
 * - 24-hour draft expiration
 * - Async restoration with proper loading order
 * - Recovery prompt UX
 * - Derived state (mixes) is regenerated, not restored
 * - Explicit save calls on structural changes
 * 
 * Usage:
 *   FormStateManager.init();                           // Initialize on page load
 *   FormStateManager.scheduleSave();                   // Call after major changes
 *   FormStateManager.clear();                          // Clear after successful submission
 */

const FormStateManager = (() => {
    const AUTO_SAVE_DELAY = 500; // milliseconds
    const MAX_DRAFT_AGE = 24 * 60 * 60 * 1000; // 24 hours
    
    let autoSaveTimeout = null;
    let currentUser = null;
    let draftWasRestored = false;
    let draftCleared = false;

    /**
     * Get user-specific storage key
     */
    function getStorageKey() {
        if (!currentUser) {
            console.warn('[FormStateManager] Current user not available');
            return 'spray_recommendation_draft_unknown';
        }
        return `spray_recommendation_draft_${currentUser}`;
    }

    /**
     * Extract current user from page (set by Flask template)
     */
    function detectCurrentUser() {
        // Try multiple sources where the user ID might be stored
        if (window.CURRENT_USER_ID) {
            currentUser = window.CURRENT_USER_ID;
        } else if (document.body.dataset.userId) {
            currentUser = document.body.dataset.userId;
        } else if (document.querySelector('meta[name="user-id"]')) {
            currentUser = document.querySelector('meta[name="user-id"]').content;
        }
        
        if (currentUser) {
            console.log('[FormStateManager] Current user:', currentUser);
        } else {
            console.warn('[FormStateManager] Could not detect current user ID');
        }
    }

    /**
     * Collect all form data into a serializable object
     * Note: Mixes are NOT saved; they are derived state to be regenerated
     */
    function collectFormState() {
        const state = {
            version: 1,
            user_id: currentUser,
            timestamp: new Date().toISOString(),
            
            // Basic fields
            spray_date: document.getElementById('spray_date')?.value || '',
            spray_description: document.getElementById('spray_description')?.value || '',
            method_id: document.getElementById('method_id')?.value || '',
            scouting_note: document.getElementById('scouting_note')?.value || '',
            warehouse_id: document.getElementById('warehouse_id')?.value || '',
            
            // Dose mode
            dose_mode: document.querySelector('input[name="dose_mode"]:checked')?.value || 'per_100l',
            
            // Global water fields
            global_water_per_tank: document.getElementById('global_water_per_tank')?.value || '',
            global_water_per_ha: document.getElementById('global_water_per_ha')?.value || '',
            global_total_water: document.getElementById('global_total_water')?.value || '',
            
            // Projects (selected option values)
            project_ids: Array.from(document.querySelectorAll('#project_ids option:checked')).map(o => o.value),
            
            // Project-level water configs
            project_configs: [],
            
            // Product lines
            product_lines: [],
            
            // Checkbox for immediate execution
            create_execution_immediately: document.getElementById('create_execution_immediately')?.checked || false,
            require_date_time: document.getElementById('require_date_time')?.checked ?? true,
            require_weather: document.getElementById('require_weather')?.checked ?? true
        };

        // Collect project-level configs (if present)
        document.querySelectorAll('.project-row:not(.project-head)').forEach((row, idx) => {
            state.project_configs.push({
                index: idx,
                water_per_ha: row.querySelector('.project-water-input')?.value || '',
                water_total: row.querySelector('.project-water-total')?.value || ''
            });
        });

        // Collect product lines
        document.querySelectorAll('.product-card').forEach((card, idx) => {
            const select = card.querySelector('.product-select');
            state.product_lines.push({
                index: idx,
                stock_id: select?.value || '',
                qty_input: card.querySelector('.qty-input')?.value || '',
                reg_number: card.querySelector('.line-reg-number')?.value || '',
                witholding_period: card.querySelector('.line-witholding-period')?.value || '',
                function: card.querySelector('.line-function')?.value || ''
            });
        });

        return state;
    }

    /**
     * Save form state to localStorage
     */
    function saveToLocalStorage(state) {
        try {
            localStorage.setItem(getStorageKey(), JSON.stringify(state));
            console.log('[FormStateManager] Draft saved to localStorage');
        } catch (err) {
            console.warn('[FormStateManager] Failed to save draft:', err);
        }
    }

    /**
     * Load form state from localStorage
     */
    function loadFromLocalStorage() {
        try {
            const stored = localStorage.getItem(getStorageKey());
            return stored ? JSON.parse(stored) : null;
        } catch (err) {
            console.warn('[FormStateManager] Failed to load draft:', err);
            return null;
        }
    }

    /**
     * Check if a saved state is valid (not expired, correct user)
     */
    function isValidDraft(state) {
        if (!state) return false;

        // Check user match
        if (state.user_id && state.user_id !== currentUser) {
            console.log('[FormStateManager] Draft belongs to different user, discarding');
            return false;
        }

        // Check age
        const draftAge = Date.now() - new Date(state.timestamp).getTime();
        if (draftAge > MAX_DRAFT_AGE) {
            console.log('[FormStateManager] Draft is older than 24 hours, discarding');
            return false;
        }

        // Check if it has meaningful content
        const hasContent = (state.project_ids && state.project_ids.length > 0) ||
                          (state.product_lines && state.product_lines.length > 0) ||
                          (state.spray_description && state.spray_description.trim().length > 0);
        
        return hasContent;
    }

    /**
     * Show recovery prompt modal
     */
    function showRecoveryPrompt(state) {
        return new Promise((resolve) => {
            if (typeof Swal === 'undefined') {
                // Fallback if SweetAlert not available
                const proceed = confirm('Unsaved spray recommendation found from ' + 
                    new Date(state.timestamp).toLocaleString() + 
                    '. Restore it?');
                resolve(proceed);
                return;
            }

            Swal.fire({
                title: 'Draft Found',
                html: `
                    <div style="text-align: left; margin: 1rem 0;">
                        <p style="margin-bottom: 0.5rem;">
                            <strong>Unsaved spray recommendation detected</strong>
                        </p>
                        <p style="color: #666; font-size: 0.9rem; margin: 0;">
                            Last saved: ${new Date(state.timestamp).toLocaleString()}
                        </p>
                        ${state.spray_description ? `<p style="margin: 0.5rem 0; font-style: italic; color: #0f172a;">"${state.spray_description}"</p>` : ''}
                    </div>
                `,
                icon: 'question',
                showCancelButton: true,
                confirmButtonText: 'Restore Draft',
                cancelButtonText: 'Start Fresh',
                confirmButtonColor: '#2563eb',
                cancelButtonColor: '#dc2626'
            }).then((result) => {
                resolve(result.isConfirmed);
            });
        });
    }

    /**
     * Restore basic fields (simple, synchronous)
     */
    function restoreBasicFields(state) {
        const fields = [
            'spray_date', 'spray_description', 'scouting_note', 
            'warehouse_id', 'global_water_per_tank', 'global_water_per_ha', 'global_total_water'
        ];
        
        fields.forEach(fieldId => {
            const el = document.getElementById(fieldId);
            if (el && state[fieldId] !== undefined && state[fieldId] !== null) {
                el.value = state[fieldId];
            }
        });

        // Restore dose mode
        if (state.dose_mode) {
            const modeRadio = document.querySelector(`input[name="dose_mode"][value="${state.dose_mode}"]`);
            if (modeRadio) {
                modeRadio.checked = true;
            }
        }

        // Restore create_execution_immediately checkbox
        const execCheckbox = document.getElementById('create_execution_immediately');
        if (execCheckbox && state.create_execution_immediately !== undefined) {
            execCheckbox.checked = state.create_execution_immediately;
        }

        const requireDateTime = document.getElementById('require_date_time');
        if (requireDateTime && state.require_date_time !== undefined) {
            requireDateTime.checked = state.require_date_time;
        }

        const requireWeather = document.getElementById('require_weather');
        if (requireWeather && state.require_weather !== undefined) {
            requireWeather.checked = state.require_weather;
        }

        console.log('[FormStateManager] Basic fields restored');
    }

    /**
     * Waits for the global PRODUCT_OPTIONS to be populated.
     * This ensures that product dropdowns can be correctly initialized.
     */
    function waitForProductsLoaded(timeoutMs = 5000) {
        return new Promise((resolve) => {
            const start = Date.now();
            const timer = setInterval(() => {
                // Check if PRODUCT_OPTIONS has real product data.
                // It must contain at least one option beyond the empty placeholder.
                const hasProducts = PRODUCT_OPTIONS && PRODUCT_OPTIONS.includes('value="') &&
                    (PRODUCT_OPTIONS.match(/<option /g) || []).length > 1;

                if (hasProducts || Date.now() - start > timeoutMs) {
                    clearInterval(timer);
                    resolve();
                }
            }, 100);
        });
    }

    /**
     * Restore complex state (projects, products, water configs)
     * This now waits for product data to be loaded before adding product lines.
     */
    async function restoreComplexState(state) {
    window.isRestoringDraft = true;
    console.log('[FormStateManager] Starting complex state restoration...');

    try {
        // 1) Restore projects. This should trigger updateProducts().
        if (state.project_ids && state.project_ids.length > 0) {
            const $projectSelect = $('#project_ids');
            $projectSelect.val(state.project_ids).trigger('change');
        }

        // 2) CRITICAL FIX: Wait for the method dropdown to be populated
        //    before trying to restore the method selection
        if (state.project_ids && state.project_ids.length > 0) {
            // First, fetch and populate the methods dropdown
            await updateMethods(state.project_ids[0]);
            
            // Wait a bit for the DOM to update after the method population
            await new Promise(r => setTimeout(r, 50));
            
            // Now restore the saved method if it exists in the dropdown
            if (state.method_id) {
                const methodSelect = document.getElementById('method_id');
                if (methodSelect) {
                    // Check if the saved method exists in the dropdown
                    const savedMethodExists = Array.from(methodSelect.options || [])
                        .some(option => String(option.value) === String(state.method_id));
                    
                    if (savedMethodExists) {
                        $(methodSelect).val(String(state.method_id)).trigger('change');
                        console.log('[FormStateManager] Method restored:', state.method_id);
                    } else {
                        console.warn('[FormStateManager] Saved method not available:', state.method_id);
                    }
                }
            }
        }

        // 3) Wait for products to be fetched and rendered
        await waitForProductsLoaded();

        // 4) Clear any lines that updateProducts may have auto-added
        clearLines();

        // 5) Add saved lines one by one
        if (state.product_lines && state.product_lines.length > 0) {
            for (const lineData of state.product_lines) {
                addLine();

                // Let Select2 init finish
                await new Promise(r => setTimeout(r, 30));

                const cards = document.querySelectorAll('.product-card');
                const card = cards[cards.length - 1];
                if (!card) continue;

                const $select = $(card.querySelector('.product-select'));

                // Set product without fighting duplicate checks across parallel lines
                if (lineData.stock_id) {
                    $select.val(String(lineData.stock_id)).trigger('change');
                }

                const qtyInput = card.querySelector('.qty-input');
                if (qtyInput && lineData.qty_input) {
                    qtyInput.value = lineData.qty_input;
                }

                card.querySelector('.line-reg-number').value = lineData.reg_number || '';
                card.querySelector('.line-witholding-period').value = lineData.witholding_period || '';
                card.querySelector('.line-function').value = lineData.function || '';
            }
        }

        // 6) Restore project water configs
        if (state.project_configs && state.project_configs.length > 0) {
            const rows = document.querySelectorAll('.project-row:not(.project-head)');
            state.project_configs.forEach(configData => {
                const row = rows[configData.index];
                if (!row) return;
                const waterInput = row.querySelector('.project-water-input');
                const totalInput = row.querySelector('.project-water-total');
                if (waterInput && configData.water_per_ha) waterInput.value = configData.water_per_ha;
                if (totalInput && configData.water_total) totalInput.value = configData.water_total;
            });
        }

        if (typeof recalcEverything === 'function') {
            recalcEverything();
        }

        draftWasRestored = true;
        console.log('[FormStateManager] Complex state restoration complete');
    } finally {
        window.isRestoringDraft = false;
    }
}

    /**
     * Initialize the form state manager
     * - Detect current user
     * - Check for valid saved draft
     * - Show recovery prompt if appropriate
     * - Restore state with proper async ordering
     */
    async function init() {
        console.log('[FormStateManager] Initializing...');

        // Detect current user
        detectCurrentUser();

        // Load and validate draft
        const savedState = loadFromLocalStorage();
        if (!isValidDraft(savedState)) {
            console.log('[FormStateManager] No valid draft found');
            setupAutoSave();
            return;
        }

        // Show recovery prompt
        const shouldRestore = await showRecoveryPrompt(savedState);
        if (!shouldRestore) {
            console.log('[FormStateManager] User chose to start fresh');
            clear();
            setupAutoSave();
            return;
        }

        console.log('[FormStateManager] User chose to restore draft');

        // Restore basic fields immediately
        restoreBasicFields(savedState);

        // Restore complex state after async project/product loading
        // We wait for updateProjects() to complete by listening for project_ids to populate
        const projectSelectWatcher = setInterval(() => {
            const $projectSelect = $('#project_ids');
            if ($projectSelect.find('option').length > 0) {
                clearInterval(projectSelectWatcher);
                restoreComplexState(savedState).then(() => {
                    setupAutoSave();
                });
            }
        }, 100);

        // Safety timeout: if projects never load, proceed anyway
        setTimeout(() => {
            clearInterval(projectSelectWatcher);
            if (!draftWasRestored) {
                setupAutoSave();
            }
        }, 5000);
    }

    /**
     * Setup auto-save event listeners
     */
    function setupAutoSave() {
        draftCleared = false;

        // Attach auto-save listeners to form inputs
        const form = document.getElementById('spray-form');
        if (form) {
            form.addEventListener('input', scheduleAutoSave);
            form.addEventListener('change', scheduleAutoSave);
        }

        // Monitor dose mode radio buttons
        document.querySelectorAll('input[name="dose_mode"]').forEach(radio => {
            radio.addEventListener('change', scheduleAutoSave);
        });

        // Monitor execution checkbox
        const execCheckbox = document.getElementById('create_execution_immediately');
        if (execCheckbox) {
            execCheckbox.addEventListener('change', scheduleAutoSave);
        }

        document.querySelectorAll('#require_date_time, #require_weather').forEach(toggle => {
            toggle.addEventListener('change', scheduleAutoSave);
        });

        console.log('[FormStateManager] Auto-save listeners attached');
    }

    /**
     * Clear the saved draft (call after successful submission)
     */
    function clear() {
        draftCleared = true;
        if (autoSaveTimeout) {
            clearTimeout(autoSaveTimeout);
            autoSaveTimeout = null;
        }

        try {
            localStorage.removeItem(getStorageKey());
            console.log('[FormStateManager] Draft cleared');
        } catch (err) {
            console.warn('[FormStateManager] Failed to clear draft:', err);
        }
    }

    function scheduleAutoSave() {
        if (draftCleared) return;

        if (autoSaveTimeout) {
            clearTimeout(autoSaveTimeout);
        }
        
        autoSaveTimeout = setTimeout(() => {
            const state = collectFormState();
            saveToLocalStorage(state);
        }, AUTO_SAVE_DELAY);
    }

    /**
     * Get the current saved state (useful for debugging)
     */
    function getState() {
        return loadFromLocalStorage();
    }

    /**
     * Explicitly trigger a save (call this after major structural changes)
     */
    function triggerSave() {
        if (draftCleared) return;

        const state = collectFormState();
        saveToLocalStorage(state);
    }

    // Public API
    return {
        init,
        clear,
        getState,
        scheduleSave: scheduleAutoSave,
        save: triggerSave
    };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => FormStateManager.init());
} else {
    FormStateManager.init();
}