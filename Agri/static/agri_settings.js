const offline = await window.sprayOfflineReady;
const form = document.getElementById('device-settings-form');
const status = document.getElementById('settings-status');

const sections = ['catalog', 'spray', 'execution'];

function setSectionVisibility(section) {
    const mode = document.querySelector(`input[name="${section}-mode"]:checked`)?.value;
    const autoOptions = document.querySelector(`.${section}-auto-options`);
    const intervalOptions = document.querySelector(`.${section}-interval-options`);
    const isAuto = mode === 'auto';
    if (autoOptions) autoOptions.hidden = !isAuto;
    const policy = document.getElementById(`${section}-auto-policy`);
    if (intervalOptions && policy) {
        intervalOptions.hidden = !isAuto || policy.value !== 'interval';
    }
}

function applySettings(settings) {
    for (const section of sections) {
        const values = settings[section];
        const mode = document.querySelector(`input[name="${section}-mode"][value="${values.mode}"]`);
        const policy = document.getElementById(`${section}-auto-policy`);
        const interval = document.getElementById(`${section}-interval`);
        if (!mode || !policy || !interval) continue;
        mode.checked = true;
        policy.value = values.auto_policy;
        interval.value = String(values.interval_ms);
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
    for (const section of sections) {
        if (!document.querySelector(`input[name="${section}-mode"]`)) continue;
        next[section] = {
            mode: document.querySelector(`input[name="${section}-mode"]:checked`).value,
            auto_policy: document.getElementById(`${section}-auto-policy`).value,
            interval_ms: Number(document.getElementById(`${section}-interval`).value)
        };
    }
    await offline.saveDeviceSettings(next);
    status.textContent = 'Saved on this device.';
});