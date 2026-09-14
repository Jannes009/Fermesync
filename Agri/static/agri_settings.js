const offline = await window.sprayOfflineReady;
const form = document.getElementById('device-settings-form');
const status = document.getElementById('settings-status');

function setSectionVisibility(section) {
    const mode = document.querySelector(`input[name="${section}-mode"]:checked`)?.value;
    const autoOptions = document.querySelector(`.${section}-auto-options`);
    const intervalOptions = document.querySelector(`.${section}-interval-options`);
    const isAuto = mode === 'auto';
    if (autoOptions) autoOptions.hidden = !isAuto;
    if (intervalOptions) {
        intervalOptions.hidden = !isAuto || document.getElementById(`${section}-auto-policy`).value !== 'interval';
    }
}

function applySettings(settings) {
    for (const section of ['catalog', 'spray']) {
        const values = settings[section];
        document.querySelector(`input[name="${section}-mode"][value="${values.mode}"]`).checked = true;
        document.getElementById(`${section}-auto-policy`).value = values.auto_policy;
        document.getElementById(`${section}-interval`).value = String(values.interval_ms);
        setSectionVisibility(section);
    }
}

const settings = await offline.readDeviceSettings();
applySettings(settings);
document.querySelectorAll('input[type="radio"], select').forEach(input => {
    input.addEventListener('change', () => setSectionVisibility(input.name?.split('-')[0] || input.id.split('-')[0]));
});

form.addEventListener('submit', async event => {
    event.preventDefault();
    const next = {};
    for (const section of ['catalog', 'spray']) {
        next[section] = {
            mode: document.querySelector(`input[name="${section}-mode"]:checked`).value,
            auto_policy: document.getElementById(`${section}-auto-policy`).value,
            interval_ms: Number(document.getElementById(`${section}-interval`).value)
        };
    }
    await offline.saveDeviceSettings(next);
    status.textContent = 'Saved on this device.';
});