/**
 * OWN API Client — REST + WebSocket helpers.
 */

const API_BASE = '';  // Same origin

/**
 * Make an API request.
 */
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const response = await fetch(url, {
        ...options,
        headers: {
            ...(!options.body || options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
            ...options.headers,
        },
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || `API Error: ${response.status}`);
    }

    // Handle file downloads
    const contentType = response.headers.get('content-type');
    if (contentType && (contentType.includes('text/plain') || contentType.includes('octet-stream'))) {
        return response;
    }

    return response.json();
}

// ── Projects ─────────────────────────────────────────────────────────────────

async function listProjects() {
    return apiRequest('/api/projects');
}

async function getProject(id) {
    return apiRequest(`/api/projects/${id}`);
}

async function createProject(file, title, language = 'hi') {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    formData.append('language', language);

    return apiRequest('/api/projects', {
        method: 'POST',
        body: formData,
    });
}

async function updateProject(id, data) {
    return apiRequest(`/api/projects/${id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

async function deleteProject(id) {
    return apiRequest(`/api/projects/${id}`, { method: 'DELETE' });
}

// ── Transcription ────────────────────────────────────────────────────────────

async function startTranscription(projectId, engine = 'vosk', language = 'hi') {
    return apiRequest(`/api/projects/${projectId}/transcribe`, {
        method: 'POST',
        body: JSON.stringify({ engine, language }),
    });
}

// ── Export ────────────────────────────────────────────────────────────────────

async function startExport(projectId, format = 'MP4 (H.264)') {
    return apiRequest(`/api/projects/${projectId}/export`, {
        method: 'POST',
        body: JSON.stringify({ format }),
    });
}

function getSrtDownloadUrl(projectId) {
    return `${API_BASE}/api/projects/${projectId}/srt`;
}

function getThumbnailUrl(projectId) {
    return `${API_BASE}/api/projects/${projectId}/thumbnail`;
}

function getVideoUrl(projectId) {
    return `${API_BASE}/api/projects/${projectId}/video`;
}

function getExportDownloadUrl(filename) {
    return `${API_BASE}/api/exports/${filename}`;
}

// ── Models ───────────────────────────────────────────────────────────────────

async function listModels() {
    return apiRequest('/api/models');
}

async function listAvailableModels() {
    return apiRequest('/api/models/available');
}

// ── Model API (Additional helpers) ───────────────────────────────────────────────

/**
 * Get list of available models with install status
 */
async function getAvailableModels() {
    const response = await fetch('/api/models/available');
    if (!response.ok) throw new Error('Failed to get available models');
    return await response.json();
}

/**
 * Get list of installed models
 */
async function getInstalledModels() {
    const response = await fetch('/api/models');
    if (!response.ok) throw new Error('Failed to get installed models');
    return await response.json();
}

async function downloadModel(name) {
    return apiRequest('/api/models/download', {
        method: 'POST',
        body: JSON.stringify({ name }),
    });
}

async function deleteModel(id) {
    return apiRequest(`/api/models/${id}`, { method: 'DELETE' });
}

/**
 * Download a model
 * @param {string} modelName - Name of the model to download
 * @param {function} onProgress - Callback for progress updates (percent, message)
 */
async function downloadModel(modelName, onProgress) {
    const { task_id } = await fetch('/api/models/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: modelName })
    }).then(r => r.json());

    return watchProgress(task_id,
        (data) => {
            if (onProgress) onProgress(data.percent, data.message);
        },
        (data) => {
            // Download complete
        },
        (error) => {
            throw new Error(error);
        }
    );
}

// ── User ─────────────────────────────────────────────────────────────────────

async function getUser() {
    return apiRequest('/api/user');
}

async function updateUser(data) {
    return apiRequest('/api/user', {
        method: 'PUT',
        body: JSON.stringify(data),
    });
}

// ── Presets ───────────────────────────────────────────────────────────────────

async function getPresets() {
    return apiRequest('/api/presets');
}

// ── WebSocket Progress ───────────────────────────────────────────────────────

function watchProgress(taskId, onUpdate, onComplete, onError) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/progress/${taskId}`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.error) {
            if (onError) onError(data.error);
            ws.close();
            return;
        }

        if (onUpdate) onUpdate(data);

        if (data.percent >= 100 || data.percent < 0) {
            if (onComplete) onComplete(data);
            ws.close();
        }
    };

    ws.onerror = (event) => {
        if (onError) onError('WebSocket connection error');
    };

    ws.onclose = () => {
        // Connection closed
    };

    return ws;
}

// ── Utility ──────────────────────────────────────────────────────────────────

function formatDuration(seconds) {
    if (!seconds) return '00:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatFileSize(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return `${size.toFixed(1)} ${units[i]}`;
}

function timeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    if (diffHours < 24) return `${diffHours} hours ago`;
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString();
}
