/**
 * OWN Home Page — app.js
 */

document.addEventListener('DOMContentLoaded', () => {
    initUploadZone();
    loadProjects();
    initSearch();
    loadUser();
});


// ── Upload Zone ──────────────────────────────────────────────────────────────

let selectedFile = null;

function initUploadZone() {
    const zone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const uploadBtn = document.getElementById('upload-btn');
    const modal = document.getElementById('upload-modal');
    const modalCancel = document.getElementById('modal-cancel');
    const modalUpload = document.getElementById('modal-upload');

    // Click to select file
    uploadBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.click();
    });
    zone.addEventListener('click', () => fileInput.click());

    // File selected
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            selectedFile = e.target.files[0];
            document.getElementById('modal-title').value = selectedFile.name.replace(/\.[^.]+$/, '');
            showModal(modal);
        }
    });

    // Drag and drop
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });
    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            selectedFile = e.dataTransfer.files[0];
            document.getElementById('modal-title').value = selectedFile.name.replace(/\.[^.]+$/, '');
            showModal(modal);
        }
    });

    // Modal actions
    modalCancel.addEventListener('click', () => {
        hideModal(modal);
        selectedFile = null;
    });

    modalUpload.addEventListener('click', () => {
        hideModal(modal);
        if (selectedFile) {
            uploadAndTranscribe(selectedFile);
        }
    });
}

async function uploadAndTranscribe(file) {
    const title = document.getElementById('modal-title').value || file.name;
    const language = document.getElementById('modal-language').value;
    const engine = document.getElementById('modal-engine').value;

    const progressDiv = document.getElementById('upload-progress');
    const statusEl = document.getElementById('upload-status');
    const barEl = document.getElementById('upload-progress-bar');

    progressDiv.classList.remove('hidden');
    statusEl.textContent = 'Uploading video...';
    barEl.style.width = '20%';

    try {
        // Step 1: Upload
        const project = await createProject(file, title, language);
        barEl.style.width = '50%';
        statusEl.textContent = 'Starting transcription...';

        // Step 2: Start transcription
        const { task_id } = await startTranscription(project.id, engine, language);
        
        // Step 3: Watch progress
        watchProgress(task_id,
            (data) => {
                barEl.style.width = `${Math.max(50, data.percent)}%`;
                statusEl.textContent = data.message;
            },
            (data) => {
                barEl.style.width = '100%';
                statusEl.textContent = 'Complete! Opening editor...';
                setTimeout(() => {
                    window.location.href = `/editor/${project.id}`;
                }, 1000);
            },
            (error) => {
                statusEl.textContent = `Error: ${error}`;
                barEl.style.width = '0%';
                showToast(error, 'error');
                setTimeout(() => {
                    progressDiv.classList.add('hidden');
                    loadProjects();
                }, 3000);
            }
        );
    } catch (err) {
        statusEl.textContent = `Upload failed: ${err.message}`;
        showToast(err.message, 'error');
        setTimeout(() => progressDiv.classList.add('hidden'), 3000);
    }
}


// ── Projects Grid ────────────────────────────────────────────────────────────

async function loadProjects() {
    const grid = document.getElementById('projects-grid');
    const empty = document.getElementById('empty-state');
    const countEl = document.getElementById('project-count');

    try {
        const projects = await listProjects();

        if (projects.length === 0) {
            grid.innerHTML = '';
            empty.classList.remove('hidden');
            countEl.textContent = '';
            return;
        }

        empty.classList.add('hidden');
        countEl.textContent = `${projects.length} project${projects.length !== 1 ? 's' : ''}`;

        grid.innerHTML = projects.map(p => createProjectCard(p)).join('');

        // Add click handlers
        grid.querySelectorAll('.project-card').forEach(card => {
            card.addEventListener('click', () => {
                const id = card.dataset.id;
                window.location.href = `/editor/${id}`;
            });
        });

        // Delete buttons
        grid.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                if (confirm('Delete this project?')) {
                    await deleteProject(id);
                    loadProjects();
                    showToast('Project deleted', 'success');
                }
            });
        });
    } catch (err) {
        grid.innerHTML = `<p class="text-red-400 col-span-3">Error loading projects: ${err.message}</p>`;
    }
}

function createProjectCard(project) {
    const statusClass = {
        'completed': 'badge-completed',
        'transcribing': 'badge-transcribing',
        'draft': 'badge-draft',
    }[project.status] || 'badge-draft';

    const statusLabel = project.status ? project.status.charAt(0).toUpperCase() + project.status.slice(1) : 'Draft';
    const langLabel = (project.language || 'hi').toUpperCase();
    const duration = formatDuration(project.video_duration);
    const updated = timeAgo(project.updated_at);

    return `
        <div class="project-card group rounded-xl border border-white/10 bg-white/5 overflow-hidden cursor-pointer" data-id="${project.id}">
            <div class="aspect-video relative bg-bg-surface">
                <img class="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" 
                     src="${getThumbnailUrl(project.id)}" 
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'"/>
                <div class="absolute inset-0 items-center justify-center hidden bg-bg-surface">
                    <span class="material-symbols-outlined text-4xl text-slate-600">movie</span>
                </div>
                <div class="absolute bottom-2 right-2 bg-black/60 backdrop-blur px-2 py-1 rounded text-[10px] text-white font-bold tracking-wider">${duration}</div>
                <button class="delete-btn absolute top-2 right-2 bg-black/60 backdrop-blur p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-500/50" data-id="${project.id}">
                    <span class="material-symbols-outlined text-white text-sm">delete</span>
                </button>
            </div>
            <div class="p-4">
                <h4 class="font-bold text-white truncate">${escapeHtml(project.title)}</h4>
                <p class="text-xs text-slate-400 mt-1">Edited ${updated}</p>
                <div class="mt-4 flex items-center gap-2">
                    <span class="text-[10px] px-2 py-0.5 rounded-full bg-primary/20 text-primary font-bold uppercase">${langLabel}</span>
                    <span class="text-[10px] px-2 py-0.5 rounded-full ${statusClass} font-bold uppercase">${statusLabel}</span>
                </div>
            </div>
        </div>
    `;
}


// ── Search ────────────────────────────────────────────────────────────────────

function initSearch() {
    const input = document.getElementById('search-input');
    input.addEventListener('input', () => {
        const query = input.value.toLowerCase().trim();
        const cards = document.querySelectorAll('.project-card');
        cards.forEach(card => {
            const title = card.querySelector('h4').textContent.toLowerCase();
            card.style.display = title.includes(query) ? '' : 'none';
        });
    });
}


// ── User ──────────────────────────────────────────────────────────────────────

async function loadUser() {
    try {
        const user = await getUser();
        if (user.name && user.name !== 'Guest') {
            document.getElementById('user-name').textContent = user.name;
        }
    } catch (e) { /* ignore */ }
}


// ── Helpers ───────────────────────────────────────────────────────────────────

function showModal(modal) {
    modal.classList.add('active');
}

function hideModal(modal) {
    modal.classList.remove('active');
}

function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
