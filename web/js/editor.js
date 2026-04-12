/**
 * OWN Editor Page — editor.js
 * Wires together: video player, subtitle preview, timeline, style controls.
 */

let project = null;
let subtitleTrack = null;
let preview = null;
let timeline = null;
let saveTimeout = null;

document.addEventListener('DOMContentLoaded', async () => {
    const projectId = getProjectIdFromUrl();
    if (!projectId) {
        alert('No project ID in URL');
        window.location.href = '/';
        return;
    }

    await loadProject(projectId);
    initVideoPlayer();
    initTimelineControls();
    initStylingSystem();
    initFullTextEditing();
    initSentenceMode();
    initExport();
    initSrtDownload();
    initTranscription();
    loadPresets();
});


// ── Load Project ─────────────────────────────────────────────────────────────

function getProjectIdFromUrl() {
    const parts = window.location.pathname.split('/');
    return parseInt(parts[parts.length - 1]) || null;
}

// Ensure subtitleTrack has required defaults after JSON load
function ensureSubtitleTrackMethods() {
    if (!subtitleTrack) return;
    if (!subtitleTrack.text_box_width) subtitleTrack.text_box_width = 0.8;
    if (!subtitleTrack.highlight_style) subtitleTrack.highlight_style = null;
    if (!subtitleTrack.spotlight_style) subtitleTrack.spotlight_style = null;
    if (subtitleTrack.sentence_mode === undefined) subtitleTrack.sentence_mode = false;
}

async function loadProject(id) {
    try {
        // Add cache-busting timestamp
        project = await getProject(`${id}?_t=${Date.now()}`);
        console.log('[loadProject] Loaded project:', project);
        console.log('[loadProject] Subtitle data:', project.subtitle_data);
        document.getElementById('project-title').textContent = project.title;

        // Load video
        const video = document.getElementById('video-player');
        video.src = getVideoUrl(id);
        video.load();

        // Parse subtitle data
        if (project.subtitle_data) {
            if (typeof project.subtitle_data === 'string') {
                subtitleTrack = JSON.parse(project.subtitle_data);
            } else {
                subtitleTrack = project.subtitle_data;
            }
            // Ensure subtitleTrack has all necessary methods
            ensureSubtitleTrackMethods();
        }

        // Initialize preview (only once)
        const canvas = document.getElementById('subtitle-canvas');
        if (!preview) {
            preview = new SubtitlePreview(video, canvas);
            preview.start();
            // Wire handle drag back to UI
            preview.onWidthChange((w) => {
                if (!subtitleTrack) return;
                const el = document.getElementById('global-text-box-width');
                const valEl = document.getElementById('global-text-box-width-val');
                if (el) el.value = Math.round((w ?? 0.8) * 100);
                if (valEl) valEl.textContent = `${Math.round((w ?? 0.8) * 100)}%`;
                autoSave();
            });
        }
        if (subtitleTrack) {
            preview.setTrack(subtitleTrack);
        }

        // Initialize timeline (only once)
        const timelineCanvas = document.getElementById('timeline-canvas');
        const timelineWrapper = document.getElementById('timeline-wrapper');
        if (!timeline) {
            timeline = new SubtitleTimeline(timelineCanvas, timelineWrapper);

            // Set up timeline callbacks (only once)
            timeline.onSeek = (time) => {
                video.currentTime = time;
            };

            timeline.onSelect = (sel) => {
                if (sel && sel.track === 'text') {
                    highlightSegment(sel.index);
                } else {
                    highlightSegment(-1);
                }
            };
        }

        if (subtitleTrack) {
            // BACKWARDS COMPATIBILITY: Initialize multi-track segments if missing
            if (!subtitleTrack.video_segments || subtitleTrack.video_segments.length === 0) {
                subtitleTrack.video_segments = [{ start: 0, end: project.video_duration, source_start: 0, source_end: project.video_duration }];
            }
            if (!subtitleTrack.audio_segments || subtitleTrack.audio_segments.length === 0) {
                subtitleTrack.audio_segments = [{ start: 0, end: project.video_duration, source_start: 0, source_end: project.video_duration }];
            }

            timeline.setData(subtitleTrack, project.video_duration, project.id);
            populateSegments(subtitleTrack.segments);
            populateFullText(subtitleTrack.segments);
            applyTrackToControls(subtitleTrack);
        }

        // Subtitle Canvas Dragging (only set up once)
        if (!canvas.hasAttribute('data-drag-setup')) {
            canvas.setAttribute('data-drag-setup', 'true');
            let isDraggingSubtitle = false;
            canvas.addEventListener('mousedown', (e) => {
                if (!subtitleTrack) return;
                const rect = canvas.getBoundingClientRect();
                const posX = subtitleTrack.position_x || 0.5;
                const posY = subtitleTrack.position_y || 0.9;
                const clickX = (e.clientX - rect.left) / rect.width;
                const clickY = (e.clientY - rect.top) / rect.height;

                // Rough hit box for subtitle text area
                if (Math.abs(clickX - posX) < 0.3 && Math.abs(clickY - posY) < 0.2) {
                    isDraggingSubtitle = true;
                } else {
                    document.getElementById('btn-play').click();
                }
            });

            window.addEventListener('mousemove', (e) => {
                if (!isDraggingSubtitle || !subtitleTrack) return;
                const rect = canvas.getBoundingClientRect();
                let x = (e.clientX - rect.left) / rect.width;
                let y = (e.clientY - rect.top) / rect.height;

                x = Math.max(0.05, Math.min(0.95, x));
                y = Math.max(0.05, Math.min(0.95, y));

                subtitleTrack.position_x = x;
                subtitleTrack.position_y = y;

                const posYSlider = document.getElementById('style-pos-y');
                const posYVal = document.getElementById('pos-y-val');
                if (posYSlider) {
                    posYSlider.value = Math.round(y * 100);
                    posYVal.textContent = `${posYSlider.value}%`;
                }
                preview.setTrack(subtitleTrack);
                autoSave();
            });

            window.addEventListener('mouseup', () => {
                isDraggingSubtitle = false;
            });
        }

    } catch (err) {
        alert(`Error loading project: ${err.message}`);
        window.location.href = '/';
    }
}


// ── Video Player ─────────────────────────────────────────────────────────────

function initVideoPlayer() {
    const video = document.getElementById('video-player');
    const playBtn = document.getElementById('btn-play');
    const muteBtn = document.getElementById('btn-mute');
    const seekBar = document.getElementById('seek-bar');
    const seekProgress = document.getElementById('seek-progress');
    const seekThumb = document.getElementById('seek-thumb');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');

    playBtn.addEventListener('click', () => {
        if (video.paused) {
            video.play();
            playBtn.querySelector('span').textContent = 'pause';
        } else {
            video.pause();
            playBtn.querySelector('span').textContent = 'play_arrow';
        }
    });

    muteBtn.addEventListener('click', () => {
        video.muted = !video.muted;
        muteBtn.querySelector('span').textContent = video.muted ? 'volume_off' : 'volume_up';
    });

    video.addEventListener('loadedmetadata', () => {
        timeTotal.textContent = formatDuration(video.duration);
    });

    video.addEventListener('timeupdate', () => {
        const pct = (video.currentTime / video.duration) * 100;
        seekProgress.style.width = `${pct}%`;
        seekThumb.style.left = `${pct}%`;
        timeCurrent.textContent = formatDuration(video.currentTime);

        if (timeline) {
            timeline.setCurrentTime(video.currentTime);
        }
    });

    video.addEventListener('ended', () => {
        playBtn.querySelector('span').textContent = 'play_arrow';
    });

    seekBar.addEventListener('click', (e) => {
        const rect = seekBar.getBoundingClientRect();
        const pct = (e.clientX - rect.left) / rect.width;
        video.currentTime = pct * video.duration;
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

        switch (e.key) {
            case ' ':
                e.preventDefault();
                playBtn.click();
                break;
            case 'ArrowLeft':
                video.currentTime = Math.max(0, video.currentTime - 5);
                break;
            case 'ArrowRight':
                video.currentTime = Math.min(video.duration, video.currentTime + 5);
                break;
        }
    });

    // Global save shortcut
    window.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            // Force immediate save instead of debounce
            if (saveTimeout) clearTimeout(saveTimeout);
            saveTimeout = setTimeout(async () => {
                if (!project || !subtitleTrack) return;
                const statusEl = document.getElementById('save-status');
                try {
                    await updateProject(project.id, { subtitle_data: subtitleTrack });
                    statusEl.textContent = 'Saved via Ctrl+S';
                    statusEl.classList.remove('text-primary');
                    showToast('Project saved!');
                } catch (err) {
                    statusEl.textContent = 'Save failed';
                    statusEl.classList.add('text-red-400');
                    showToast('Failed to save project', 'error');
                }
            }, 0);
        }
    });
}


// ── Timeline Controls ────────────────────────────────────────────────────────

function initTimelineControls() {
    const btnSplit = document.getElementById('btn-split');
    const btnTrim = document.getElementById('btn-trim');

    if (btnSplit) {
        btnSplit.addEventListener('click', () => {
            if (!timeline || !subtitleTrack) return;
            const time = timeline.currentTime;
            let splitOccurred = false;

            // For ALL tracks (video, audio, text), split the segment that intersects with `time`
            const splitTrackSegments = (trackName, segList) => {
                if (!segList) return;
                const sIdx = segList.findIndex(seg => {
                    const start = (trackName === 'text') ? (seg.words?.[0]?.start_time || 0) : seg.start;
                    const end = (trackName === 'text') ? (seg.words?.[seg.words.length - 1]?.end_time || 0) : seg.end;
                    return time > start && time < end; // Strict inequality to avoid splitting exactly at borders
                });

                if (sIdx !== -1) {
                    const seg = segList[sIdx];
                    if (trackName === 'text') {
                        if (!seg.words || seg.words.length < 2) return;
                        let wIdx = seg.words.findIndex(w => (w.start_time <= time && w.end_time >= time) || w.start_time >= time);
                        if (wIdx <= 0 || wIdx >= seg.words.length) return; // Cannot split if on edges

                        const seg1 = { ...seg, words: seg.words.slice(0, wIdx) };
                        const seg2 = { ...seg, words: seg.words.slice(wIdx) };
                        segList.splice(sIdx, 1, seg1, seg2);
                        splitOccurred = true;
                    } else {
                        // MediaSegment
                        const ratio = (time - seg.start) / (seg.end - seg.start);
                        const sourceTime = seg.source_start + (seg.source_end - seg.source_start) * ratio;
                        const seg1 = { ...seg, end: time, source_end: sourceTime };
                        const seg2 = { ...seg, start: time, source_start: sourceTime };
                        segList.splice(sIdx, 1, seg1, seg2);
                        splitOccurred = true;
                    }
                }
            };

            splitTrackSegments('video', subtitleTrack.video_segments);
            splitTrackSegments('audio', subtitleTrack.audio_segments);
            splitTrackSegments('text', subtitleTrack.segments);

            if (splitOccurred) {
                timeline.setData(subtitleTrack, project.video_duration, project.id);
                populateSegments(subtitleTrack.segments);
                populateFullText(subtitleTrack.segments);
                autoSave();
                showToast('Tracks split at playhead');
            } else {
                showToast('No segments span across the playhead to split', 'error');
            }
        });
    }

    if (btnTrim) {
        btnTrim.addEventListener('click', () => {
            if (!timeline || !subtitleTrack) return;

            if (timeline.selectionRange) {
                const { start, end } = timeline.selectionRange;
                if (end <= start) return;
                const cutDuration = end - start;

                // Helper to trim a media segment list
                const trimMediaList = (segList) => {
                    const newList = [];
                    for (let seg of segList) {
                        if (seg.end <= start) {
                            newList.push(seg);
                        } else if (seg.start >= end) {
                            // Shift left
                            newList.push({ ...seg, start: seg.start - cutDuration, end: seg.end - cutDuration });
                        } else {
                            // Intersects
                            if (seg.start < start) {
                                // Keep left part
                                const r1 = (start - seg.start) / (seg.end - seg.start);
                                newList.push({ ...seg, end: start, source_end: seg.source_start + (seg.source_end - seg.source_start) * r1 });
                            }
                            if (seg.end > end) {
                                // Keep right part, shifted left
                                const r2 = (end - seg.start) / (seg.end - seg.start);
                                newList.push({ ...seg, start: start, end: seg.end - cutDuration, source_start: seg.source_start + (seg.source_end - seg.source_start) * r2 });
                            }
                        }
                    }
                    return newList;
                };

                subtitleTrack.video_segments = trimMediaList(subtitleTrack.video_segments);
                subtitleTrack.audio_segments = trimMediaList(subtitleTrack.audio_segments);

                // Helper to trim text list
                const newTextList = [];
                for (let seg of subtitleTrack.segments) {
                    const sStart = seg.words?.[0]?.start_time || 0;
                    const sEnd = seg.words?.[seg.words.length - 1]?.end_time || 0;

                    if (sEnd <= start) {
                        newTextList.push(seg);
                    } else if (sStart >= end) {
                        // Shift words left
                        const newSeg = { ...seg, words: seg.words.map(w => ({ ...w, start_time: w.start_time - cutDuration, end_time: w.end_time - cutDuration })) };
                        newTextList.push(newSeg);
                    } else {
                        // Word by word trimming
                        const newWords = [];
                        for (let w of seg.words) {
                            if (w.end_time <= start) {
                                newWords.push(w);
                            } else if (w.start_time >= end) {
                                newWords.push({ ...w, start_time: w.start_time - cutDuration, end_time: w.end_time - cutDuration });
                            }
                            // Else drop words inside cut area
                        }
                        if (newWords.length > 0) {
                            newTextList.push({ ...seg, words: newWords });
                        }
                    }
                }
                subtitleTrack.segments = newTextList;

                project.video_duration = Math.max(0, project.video_duration - cutDuration);
                timeline.duration = project.video_duration;
                timeline.selectionRange = null;
                timeline.selectedIndex = { track: null, index: -1 };

                timeline.setData(subtitleTrack, project.video_duration, project.id);
                populateSegments(subtitleTrack.segments);
                populateFullText(subtitleTrack.segments);
                autoSave();
                showToast('Selection range trimmed');
            } else if (timeline.selectedIndex && timeline.selectedIndex.index !== -1) {
                // Delete the specific selected segment completely
                const track = timeline.selectedIndex.track;
                const idx = timeline.selectedIndex.index;
                let targetList = null;
                if (track === 'video') targetList = subtitleTrack.video_segments;
                else if (track === 'audio') targetList = subtitleTrack.audio_segments;
                else if (track === 'text') targetList = subtitleTrack.segments;

                if (targetList && idx < targetList.length) {
                    targetList.splice(idx, 1);
                    timeline.selectedIndex = { track: null, index: -1 };
                    timeline.setData(subtitleTrack, project.video_duration, project.id);
                    populateSegments(subtitleTrack.segments);
                    populateFullText(subtitleTrack.segments);
                    autoSave();
                    showToast(`${track} Segment deleted`);
                }
            } else {
                showToast('Please Shift+Drag a time range or click a segment to trim', 'error');
            }
        });
    }
}


// ── Segments Panel ───────────────────────────────────────────────────────────

function populateSegments(segments) {
    const panel = document.getElementById('segments-panel');

    if (!segments || segments.length === 0) {
        panel.innerHTML = '<p class="text-sm text-slate-400">No transcript segments.</p>';
        return;
    }

    panel.innerHTML = segments.map((seg, idx) => {
        const startTime = seg.words?.[0]?.start_time || 0;
        const endTime = seg.words?.[seg.words.length - 1]?.end_time || 0;
        const text = seg.words?.map(w => w.word).join(' ') || '';
        return `
            <div class="segment-item p-2 rounded-lg border border-transparent hover:border-white/10 hover:bg-white/5 cursor-pointer transition-all" data-idx="${idx}">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-[10px] text-primary font-mono">${formatDuration(startTime)}</span>
                    <span class="text-[10px] text-slate-500">→</span>
                    <span class="text-[10px] text-primary font-mono">${formatDuration(endTime)}</span>
                </div>
                <p class="text-sm text-slate-200 leading-relaxed">${escapeHtml(text)}</p>
            </div>
        `;
    }).join('');

    // Click handler
    panel.querySelectorAll('.segment-item').forEach(item => {
        item.addEventListener('click', () => {
            const idx = parseInt(item.dataset.idx);
            const seg = segments[idx];
            const startTime = seg.words?.[0]?.start_time || 0;
            document.getElementById('video-player').currentTime = startTime;
            if (timeline) {
                timeline.selectedIndex = { track: 'text', index: idx };
                timeline.draw();
            }
            highlightSegment(idx);
        });
    });
}

function highlightSegment(idx) {
    document.querySelectorAll('.segment-item').forEach((el, i) => {
        el.classList.toggle('border-primary/30', i === idx);
        el.classList.toggle('bg-primary/5', i === idx);
    });

    // When a segment is selected from the timeline, switch to Standard tab
    if (idx >= 0) {
        switchToMarkerTab('standard');
        updateEditingIndicators();
    }
}

function populateFullText(segments) {
    const textarea = document.getElementById('fulltext-area');
    if (!segments) return;
    if (subtitleTrack?.sentence_mode) {
        // In sentence mode each segment is one sentence, join with \n
        textarea.value = segments.map(seg => seg.words?.map(w => w.word).join(' ') || '').join('\n');
    } else {
        textarea.value = segments.map(seg => seg.words?.map(w => w.word).join(' ') || '').join('\n');
    }
}

function initFullTextEditing() {
    const textarea = document.getElementById('fulltext-area');
    if (!textarea) return;

    textarea.addEventListener('input', () => {
        if (!subtitleTrack || !subtitleTrack.segments) return;

        if (subtitleTrack.sentence_mode) {
            // Sentence mode: each line delimited by \n is one segment
            resegmentBySentence(textarea.value);
        } else {
            resegmentByWords(textarea.value);
        }

        populateSegments(subtitleTrack.segments);
        preview?.setTrack(subtitleTrack);
        timeline?.setData(subtitleTrack, project.video_duration, project.id);
        autoSave();
    });
}

/** Re-segment using \n as sentence boundaries. */
function resegmentBySentence(rawText) {
    if (!subtitleTrack) return;

    // Collect all words in order with their original timings
    const allWords = [];
    for (const seg of subtitleTrack.segments) {
        if (seg.words) allWords.push(...seg.words);
    }

    // Parse sentences — split by real newlines
    const lines = rawText.split('\n');
    const newSegments = [];
    let wordCursor = 0;

    for (const line of lines) {
        const tokens = line.trim().split(/\s+/).filter(t => t);
        if (!tokens.length) continue;

        const segWords = [];
        for (const token of tokens) {
            const base = allWords[wordCursor];
            const prevEnd = segWords.length > 0
                ? segWords[segWords.length - 1].end_time
                : (base?.start_time ?? wordCursor * 0.5);
            segWords.push({
                word: token,
                start_time: base?.start_time ?? prevEnd,
                end_time: base?.end_time ?? prevEnd + 0.5,
                confidence: base?.confidence ?? 1.0,
                marker: base?.marker ?? 'standard'
            });
            if (base) wordCursor++;
        }
        newSegments.push({ words: segWords, style: subtitleTrack.global_style ? { ...subtitleTrack.global_style } : {} });
    }

    subtitleTrack.segments = newSegments;
}

/** Re-segment using words_per_line, preserving timings. */
function resegmentByWords(rawText) {
    if (!subtitleTrack) return;

    const allWords = [];
    for (const seg of subtitleTrack.segments) {
        if (seg.words) allWords.push(...seg.words);
    }

    const lines = rawText.split('\n');
    const newSegments = [];
    let wordCursor = 0;

    for (let i = 0; i < Math.max(lines.length, subtitleTrack.segments.length); i++) {
        const oldSeg = subtitleTrack.segments[i];
        const lineText = lines[i] || '';
        const newWords = lineText.trim().split(/\s+/).filter(w => w);
        const updatedWords = [];

        if (newWords.length > 0 && oldSeg?.words?.length > 0) {
            for (let j = 0; j < newWords.length; j++) {
                const oldWord = oldSeg.words[j];
                const lastEnd = updatedWords.length > 0 ? updatedWords[updatedWords.length - 1].end_time : (oldSeg.words[0]?.start_time ?? 0);
                updatedWords.push({
                    word: newWords[j],
                    start_time: oldWord?.start_time ?? lastEnd,
                    end_time: oldWord?.end_time ?? lastEnd + 0.5,
                    confidence: oldWord?.confidence ?? 1.0,
                    marker: oldWord?.marker ?? 'standard'
                });
            }
            newSegments.push({ words: updatedWords, style: oldSeg.style || {} });
        } else if (lineText.trim()) {
            const words = lineText.trim().split(/\s+/).map((w, idx) => ({
                word: w,
                start_time: idx * 0.5,
                end_time: (idx + 1) * 0.5,
                confidence: 1.0,
                marker: 'standard'
            }));
            newSegments.push({ words, style: subtitleTrack.global_style ? { ...subtitleTrack.global_style } : {} });
        }
    }

    subtitleTrack.segments = newSegments;
}

/** Sentence mode toggle. */
function initSentenceMode() {
    const chk = document.getElementById('sentence-mode-toggle');
    if (!chk) return;

    chk.addEventListener('change', () => {
        if (!subtitleTrack) return;
        subtitleTrack.sentence_mode = chk.checked;

        // Enable/disable words-per-line control
        const wplEl = document.getElementById('global-wpl');
        const wplWrap = document.getElementById('wpl-wrap');
        if (wplEl) wplEl.disabled = chk.checked;
        if (wplWrap) wplWrap.classList.toggle('opacity-40', chk.checked);

        // Immediately re-segment using current fulltext content
        const textarea = document.getElementById('fulltext-area');
        if (textarea) {
            if (chk.checked) {
                resegmentBySentence(textarea.value);
            } else {
                resegmentByWords(textarea.value);
            }
        }

        populateSegments(subtitleTrack.segments);
        preview?.setTrack(subtitleTrack);
        timeline?.setData(subtitleTrack, project.video_duration, project.id);
        autoSave();
    });
}


// ── Style Controls ───────────────────────────────────────────────────────────

// Note: initStyleControls has been replaced by initGlobalStyleControls
// which uses the new ID structure (global-*, special-*)

function updateStyle(prop, value) {
    if (!subtitleTrack) return;

    // Update global style
    if (subtitleTrack.global_style) {
        subtitleTrack.global_style[prop] = value;
    }

    // Update all segment styles
    if (subtitleTrack.segments) {
        for (const seg of subtitleTrack.segments) {
            if (seg.style) {
                seg.style[prop] = value;
            }
        }
    }

    preview?.setTrack(subtitleTrack);
    autoSave();
}

function applyTrackToControls(track) {
    const style = track.global_style || {};

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
    };
    const setText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    };

    // §1 Font
    setVal('global-font', style.font_family || 'Noto Sans Devanagari');
    setVal('global-font-size', style.font_size || 48);
    setText('global-font-size-val', style.font_size || 48);
    setVal('global-font-weight', style.font_weight || 400);
    setText('global-font-weight-val', style.font_weight || 400);
    setVal('global-font-style', style.font_style || 'normal');
    setVal('global-text-transform', style.text_transform || 'none');

    // §2 Fill
    setVal('global-fill-type', style.fill_type || 'solid');
    setVal('global-text-color', style.text_color || '#FFFFFF');
    setVal('global-grad-color1', style.gradient_color1 || '#FFFFFF');
    setVal('global-grad-color2', style.gradient_color2 || '#FFD700');
    setVal('global-grad-angle', style.gradient_angle || 0);
    setText('global-grad-angle-val', `${style.gradient_angle || 0}°`);
    setVal('global-grad-type', style.gradient_type || 'linear');
    toggleFillControls('global', style.fill_type || 'solid');

    // §3 Stroke
    const strokeCheck = document.getElementById('global-stroke-enabled');
    if (strokeCheck) strokeCheck.checked = style.stroke_enabled !== false;
    setVal('global-outline-color', style.outline_color || '#000000');
    setVal('global-outline-width', style.outline_width ?? 2);
    setText('global-outline-w-val', style.outline_width ?? 2);
    toggleStrokeControls('global', style.stroke_enabled !== false);

    // §4 Shadow
    const shadowCheck = document.getElementById('global-shadow-enabled');
    if (shadowCheck) shadowCheck.checked = style.shadow_enabled !== false;
    setVal('global-shadow-color', (style.shadow_color || '#000000').replace(/^#../, '#'));
    setVal('global-shadow-blur', style.shadow_blur || 0);
    setText('global-shadow-blur-val', style.shadow_blur || 0);
    setVal('global-shadow-ox', style.shadow_offset_x ?? 2);
    setText('global-shadow-ox-val', style.shadow_offset_x ?? 2);
    setVal('global-shadow-oy', style.shadow_offset_y ?? 2);
    setText('global-shadow-oy-val', style.shadow_offset_y ?? 2);
    toggleShadowControls('global', style.shadow_enabled !== false);

    // §5 Spacing
    setVal('global-letter-spacing', style.letter_spacing || 0);
    setText('global-letter-spacing-val', style.letter_spacing || 0);
    setVal('global-word-spacing', style.word_spacing || 0);
    setText('global-word-spacing-val', style.word_spacing || 0);
    setVal('global-line-height', style.line_height || 1.2);
    setText('global-line-height-val', style.line_height || 1.2);

    // §6 Opacity
    setVal('global-opacity', Math.round((style.text_opacity ?? 1) * 100));
    setText('global-opacity-val', Math.round((style.text_opacity ?? 1) * 100));

    // Video section
    setVal('global-vid-rotation', track.video_rotation || 0);
    setText('global-vid-rot-val', `${track.video_rotation || 0}°`);
    setVal('global-vid-rotation-input', track.video_rotation || 0);
    const video = document.getElementById('video-player');
    if (video) video.style.transform = `rotate(${track.video_rotation || 0}deg)`;
    setVal('global-sub-rotation', style.rotation || 0);
    setText('global-sub-rot-val', `${style.rotation || 0}°`);
    setVal('global-sub-rotation-input', style.rotation || 0);
    setVal('global-wpl', track.words_per_line || 4);
    setText('global-wpl-val', track.words_per_line || 4);

    // Text box width
    const tbw = Math.round((track.text_box_width ?? 0.8) * 100);
    setVal('global-text-box-width', tbw);
    setText('global-text-box-width-val', `${tbw}%`);

    // Sentence mode
    const smChk = document.getElementById('sentence-mode-toggle');
    if (smChk) smChk.checked = !!track.sentence_mode;
    const wplEl = document.getElementById('global-wpl');
    const wplWrap = document.getElementById('wpl-wrap');
    if (wplEl) wplEl.disabled = !!track.sentence_mode;
    if (wplWrap) wplWrap.classList.toggle('opacity-40', !!track.sentence_mode);

    // Animation
    setVal('global-animation', track.animation_type || 'none');
    setVal('global-anim-duration', track.animation_duration || 0.3);
    setText('global-anim-dur-val', `${track.animation_duration || 0.3}s`);
}

// Toggle fill controls visibility
function toggleFillControls(prefix, fillType) {
    const solid = document.getElementById(`${prefix}-solid-controls`);
    const gradient = document.getElementById(`${prefix}-gradient-controls`);
    if (solid) solid.classList.toggle('hidden', fillType !== 'solid');
    if (gradient) gradient.classList.toggle('hidden', fillType !== 'gradient');
}

// Toggle stroke controls visibility
function toggleStrokeControls(prefix, enabled) {
    const controls = document.getElementById(`${prefix}-stroke-controls`);
    if (controls) controls.style.opacity = enabled ? '1' : '0.3';
    if (controls) controls.style.pointerEvents = enabled ? 'auto' : 'none';
}

// Toggle shadow controls visibility
function toggleShadowControls(prefix, enabled) {
    const controls = document.getElementById(`${prefix}-shadow-controls`);
    if (controls) controls.style.opacity = enabled ? '1' : '0.3';
    if (controls) controls.style.pointerEvents = enabled ? 'auto' : 'none';
}


// ── Auto-save ────────────────────────────────────────────────────────────────

function autoSave() {
    const statusEl = document.getElementById('save-status');
    statusEl.textContent = 'Unsaved';
    statusEl.classList.add('text-primary');

    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(async () => {
        if (!project || !subtitleTrack) return;
        try {
            await updateProject(project.id, {
                subtitle_data: subtitleTrack,
            });
            statusEl.textContent = 'Saved';
            statusEl.classList.remove('text-primary');
        } catch (err) {
            statusEl.textContent = 'Save failed';
            statusEl.classList.add('text-red-400');
        }
    }, 1500);
}


// ── Tab Switching ────────────────────────────────────────────────────────────

function initTabSwitching() {
    // Left panel tabs (segments / fulltext)
    const leftTabs = document.querySelectorAll('[data-tab="segments"], [data-tab="fulltext"]');
    leftTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            leftTabs.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('segments-panel').classList.toggle('hidden', btn.dataset.tab !== 'segments');
            document.getElementById('fulltext-panel').classList.toggle('hidden', btn.dataset.tab !== 'fulltext');
        });
    });

    // Right panel tabs (text-style / templates / animation)
    const rightTabs = document.querySelectorAll('[data-tab="text-style"], [data-tab="templates"], [data-tab="animation"]');
    rightTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            rightTabs.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('text-style-panel').classList.toggle('hidden', btn.dataset.tab !== 'text-style');
            document.getElementById('templates-panel').classList.toggle('hidden', btn.dataset.tab !== 'templates');
            document.getElementById('animation-panel').classList.toggle('hidden', btn.dataset.tab !== 'animation');
        });
    });
}


// ── Presets / Templates ──────────────────────────────────────────────────────

async function loadPresets() {
    const templatePanels = [
        document.getElementById('all-templates-panel'),
        document.getElementById('presets-templates-panel')
    ].filter(Boolean);

    if (templatePanels.length === 0) {
        console.warn('[loadPresets] No template panels found');
        return;
    }

    try {
        const presets = await getPresets();
        if (!presets.length) {
            templatePanels.forEach(p => { p.innerHTML = '<p class="text-sm text-slate-400">No presets available.</p>'; });
            return;
        }

        const buildHtml = (preset, idx) => {
            const ss = preset.standard_style || preset.style || {};
            return `
            <div class="preset-card p-3 rounded-lg border border-white/10 bg-white/5 cursor-pointer hover:border-primary/30 transition-all" data-idx="${idx}">
                <div class="text-sm font-bold text-white mb-1">${escapeHtml(preset.name)}</div>
                <div class="text-xs text-slate-400 mb-2">${escapeHtml(preset.description || '')}</div>
                <div class="text-base font-bold" style="color: ${ss.text_color || '#fff'}; text-shadow: 1px 1px 2px ${ss.outline_color || '#000'};">
                    Sample सैम्पल
                </div>
            </div>`;
        };

        templatePanels.forEach(panel => {
            panel.innerHTML = presets.map(buildHtml).join('');
            panel.querySelectorAll('.preset-card').forEach(card => {
                card.addEventListener('click', () => {
                    const preset = presets[parseInt(card.dataset.idx)];
                    if (!preset || !subtitleTrack) return;

                    const ss = preset.standard_style || preset.style || {};
                    const hs = preset.highlight_style || null;
                    const sps = preset.spotlight_style || null;

                    // Apply standard style globally
                    subtitleTrack.global_style = { ...subtitleTrack.global_style, ...ss };
                    if (subtitleTrack.segments) {
                        for (const seg of subtitleTrack.segments) {
                            seg.style = { ...seg.style, ...ss };
                        }
                    }
                    if (hs) subtitleTrack.highlight_style = { ...subtitleTrack.highlight_style, ...hs };
                    if (sps) subtitleTrack.spotlight_style = { ...subtitleTrack.spotlight_style, ...sps };

                    preview?.setTrack(subtitleTrack);
                    applyTrackToControls(subtitleTrack);
                    autoSave();
                    showToast(`Applied "${preset.name}"`);
                });
            });
        });

        // Save-my-preset button
        const saveBtn = document.getElementById('btn-save-preset');
        if (saveBtn) {
            saveBtn.addEventListener('click', async () => {
                if (!subtitleTrack) return;
                const name = prompt('Enter preset name:');
                if (!name?.trim()) return;
                try {
                    await fetch('/api/presets', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name: name.trim(),
                            standard_style: subtitleTrack.global_style,
                            highlight_style: subtitleTrack.highlight_style,
                            spotlight_style: subtitleTrack.spotlight_style
                        })
                    });
                    showToast(`Preset "${name.trim()}" saved!`);
                    loadPresets();
                } catch (e) {
                    showToast('Failed to save preset', 'error');
                }
            });
        }
    } catch (err) {
        console.error('Failed to load presets:', err);
        templatePanels.forEach(p => { p.innerHTML = '<p class="text-sm text-red-400">Error loading presets.</p>'; });
    }
}


// ── Export ────────────────────────────────────────────────────────────────────

function initExport() {
    const modal = document.getElementById('export-modal');
    const btnExport = document.getElementById('btn-export');
    const btnCancel = document.getElementById('export-cancel');
    const btnStart = document.getElementById('export-start');

    btnExport.addEventListener('click', () => showModal(modal));
    btnCancel.addEventListener('click', () => hideModal(modal));

    btnStart.addEventListener('click', async () => {
        const format = document.getElementById('export-format').value;
        const progressWrap = document.getElementById('export-progress-wrap');
        const statusEl = document.getElementById('export-status');
        const barEl = document.getElementById('export-progress-bar');
        const buttons = document.getElementById('export-buttons');
        const done = document.getElementById('export-done');

        progressWrap.classList.remove('hidden');
        buttons.classList.add('hidden');

        try {
            const { task_id } = await startExport(project.id, format);

            watchProgress(task_id,
                (data) => {
                    barEl.style.width = `${data.percent}%`;
                    statusEl.textContent = data.message;
                },
                (data) => {
                    progressWrap.classList.add('hidden');
                    if (data.result?.filename) {
                        done.classList.remove('hidden');
                        document.getElementById('export-download-link').href = getExportDownloadUrl(data.result.filename);
                    }
                    showToast('Export complete!');
                },
                (error) => {
                    progressWrap.classList.add('hidden');
                    buttons.classList.remove('hidden');
                    showToast(`Export error: ${error}`, 'error');
                }
            );
        } catch (err) {
            progressWrap.classList.add('hidden');
            buttons.classList.remove('hidden');
            showToast(err.message, 'error');
        }
    });
}


// ── SRT Download ─────────────────────────────────────────────────────────────

function initSrtDownload() {
    document.getElementById('btn-srt').addEventListener('click', () => {
        if (project) {
            window.open(getSrtDownloadUrl(project.id), '_blank');
        }
    });
}


// ── Transcription ─────────────────────────────────────────────────────────────

function initTranscription() {
    const modal = document.getElementById('transcribe-modal');
    const btnTranscribe = document.getElementById('btn-transcribe');
    const btnCancel = document.getElementById('transcribe-cancel');
    const btnStart = document.getElementById('transcribe-start');
    if (!modal || !btnTranscribe || !btnCancel || !btnStart) return;

    // Words per line slider
    const wplSlider = document.getElementById('transcribe-wpl');
    const wplVal = document.getElementById('transcribe-wpl-val');
    if (wplSlider && wplVal) {
        wplSlider.addEventListener('input', () => { wplVal.textContent = wplSlider.value; });
    }

    btnTranscribe.addEventListener('click', () => showModal(modal));
    btnCancel.addEventListener('click', () => hideModal(modal));

    btnStart.addEventListener('click', async () => {
        // Whisper only — model selector specifies which Whisper model
        const model = document.getElementById('transcribe-model')?.value || 'whisper-large-v3-turbo';
        const language = project?.language || 'hi';
        const wordsPerLine = parseInt(document.getElementById('transcribe-wpl')?.value || '4');

        const progressWrap = document.getElementById('transcribe-progress-wrap');
        const statusEl = document.getElementById('transcribe-status');
        const barEl = document.getElementById('transcribe-progress-bar');
        const buttons = document.getElementById('transcribe-buttons');

        progressWrap.classList.remove('hidden');
        buttons.classList.add('hidden');

        try {
            const { task_id } = await startTranscription(project.id, {
                engine: 'whisper',
                language,
                model,
                words_per_line: wordsPerLine
            });

            watchProgress(task_id,
                (data) => {
                    barEl.style.width = `${data.percent}%`;
                    statusEl.textContent = data.message;
                },
                (data) => {
                    progressWrap.classList.add('hidden');
                    buttons.classList.remove('hidden');
                    hideModal(modal);
                    showToast('Transcription complete!');
                    setTimeout(() => loadProject(project.id), 500);
                },
                (error) => {
                    progressWrap.classList.add('hidden');
                    buttons.classList.remove('hidden');
                    showToast(`Transcription error: ${error}`, 'error');
                }
            );
        } catch (err) {
            progressWrap.classList.add('hidden');
            buttons.classList.remove('hidden');
            showToast(err.message, 'error');
        }
    });
}


// ── Helpers ──────────────────────────────────────────────────────────────────

function showModal(modal) { modal.classList.add('active'); }
function hideModal(modal) { modal.classList.remove('active'); }

function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 3000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}


// ── Model Selection ───────────────────────────────────────────────────────────

let availableModels = [];
let installedModels = [];

async function initModelSelection() {
    try {
        availableModels = await getAvailableModels();
        installedModels = await getInstalledModels();
        updateModelUI();
    } catch (err) {
        console.error('Failed to load models:', err);
    }
}

function updateModelUI() {
    const engineSelect = document.getElementById('transcribe-engine');
    const whisperSection = document.getElementById('whisper-model-section');
    const modelSelect = document.getElementById('transcribe-model');
    const modelStatus = document.getElementById('model-status');
    const downloadBtn = document.getElementById('download-model-btn');

    if (!engineSelect) return;

    // Show/hide Whisper section based on engine selection
    engineSelect.addEventListener('change', () => {
        if (engineSelect.value === 'whisper') {
            whisperSection.classList.remove('hidden');
            updateWhisperModelStatus();
        } else {
            whisperSection.classList.add('hidden');
        }
    });

    // Update Whisper model status
    updateWhisperModelStatus();

    // Download button handler
    downloadBtn.addEventListener('click', async () => {
        const modelName = modelSelect.value;
        downloadBtn.disabled = true;
        downloadBtn.textContent = 'Downloading...';
        modelStatus.textContent = 'Starting download...';

        try {
            await downloadModel(modelName, (percent, message) => {
                downloadBtn.textContent = `Downloading ${percent}%`;
                modelStatus.textContent = message;
            });

            // Refresh model list
            installedModels = await getInstalledModels();
            updateWhisperModelStatus();
            showToast('Model downloaded successfully!');
        } catch (err) {
            modelStatus.textContent = `Error: ${err.message}`;
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Download Model';
        }
    });
}

function updateWhisperModelStatus() {
    const modelSelect = document.getElementById('transcribe-model');
    const modelStatus = document.getElementById('model-status');
    const downloadBtn = document.getElementById('download-model-btn');

    if (!modelSelect) return;

    const selectedModel = modelSelect.value;
    const installed = installedModels.find(m => m.name === selectedModel);

    if (installed) {
        modelStatus.textContent = '✓ Model installed';
        modelStatus.classList.add('text-green-400');
        modelStatus.classList.remove('text-red-400');
        downloadBtn.classList.add('hidden');
    } else {
        const modelInfo = availableModels.find(m => m.name === selectedModel);
        if (modelInfo) {
            modelStatus.textContent = `Model not installed (${modelInfo.size_mb} MB)`;
            modelStatus.classList.remove('text-green-400');
            modelStatus.classList.add('text-red-400');
            downloadBtn.classList.remove('hidden');
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Download Model';
        }
    }
}

// Initialize model selection on page load
document.addEventListener('DOMContentLoaded', () => {
    initModelSelection();
});


// ── Word Selection & Marker System ────────────────────────────────────────────

// Track selected words: array of {segmentIndex, wordIndex}
let selectedWords = [];

// Currently active marker tab: 'highlight' | 'spotlight'
let currentMarkerTab = 'highlight';

// Initialize the new styling system
function initStylingSystem() {
    initTabSwitching(); // Left panel tabs (Segments / Full Text)
    initMainTabSwitching();
    initSubTabSwitching();
    initContextMenu();
    initMarkerStyleControls();
    initGlobalStyleControls();
    initDeselectOnEscape();
}

// Main tab switching (Standard / Highlight / Spotlight → maps to Style/Video/Presets sections)
function initMainTabSwitching() {
    document.querySelectorAll('[data-main-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-main-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.mainTab;
            document.getElementById('style-section')?.classList.toggle('hidden', tab !== 'style');
            document.getElementById('video-section')?.classList.toggle('hidden', tab !== 'video');
            document.getElementById('presets-section')?.classList.toggle('hidden', tab !== 'presets');
        });
    });
}

// Sub tab switching: Standard / Highlight / Spotlight
function initSubTabSwitching() {
    // Main marker sub tabs: Standard / Highlight / Spotlight
    document.querySelectorAll('[data-main-marker-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-main-marker-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.mainMarkerTab;
            if (tab === 'standard') {
                document.getElementById('all-subsection')?.classList.remove('hidden');
                document.getElementById('specials-subsection')?.classList.add('hidden');
            } else {
                document.getElementById('all-subsection')?.classList.add('hidden');
                document.getElementById('specials-subsection')?.classList.remove('hidden');
                currentMarkerTab = tab;
                loadMarkerStyleToControls(tab);
            }
            updateMarkersPanel();
        });
    });

    // All subsection tabs
    document.querySelectorAll('[data-all-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-all-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.allTab;
            document.getElementById('all-text-panel')?.classList.toggle('hidden', tab !== 'text');
            document.getElementById('all-templates-panel')?.classList.toggle('hidden', tab !== 'templates');
            document.getElementById('all-animation-panel')?.classList.toggle('hidden', tab !== 'animation');
        });
    });

    // Presets section tabs
    document.querySelectorAll('[data-preset-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-preset-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.presetTab;
            document.getElementById('presets-panel')?.classList.toggle('hidden', tab !== 'presets');
            document.getElementById('presets-templates-panel')?.classList.toggle('hidden', tab !== 'templates');
        });
    });
}

/**
 * Programmatically switch to a marker tab ('standard' | 'highlight' | 'spotlight').
 * Keeps the UI and state in sync.
 */
function switchToMarkerTab(tab) {
    // Activate the correct sub-tab button
    document.querySelectorAll('[data-main-marker-tab]').forEach(b => b.classList.remove('active'));
    const targetBtn = document.querySelector(`[data-main-marker-tab="${tab}"]`);
    if (targetBtn) targetBtn.classList.add('active');

    // Also make sure we're on the Style main tab
    document.querySelectorAll('[data-main-tab]').forEach(b => b.classList.remove('active'));
    const styleBtn = document.querySelector('[data-main-tab="style"]');
    if (styleBtn) styleBtn.classList.add('active');
    document.getElementById('style-section')?.classList.remove('hidden');
    document.getElementById('video-section')?.classList.add('hidden');
    document.getElementById('presets-section')?.classList.add('hidden');

    if (tab === 'standard') {
        document.getElementById('all-subsection')?.classList.remove('hidden');
        document.getElementById('specials-subsection')?.classList.add('hidden');
    } else {
        document.getElementById('all-subsection')?.classList.add('hidden');
        document.getElementById('specials-subsection')?.classList.remove('hidden');
        currentMarkerTab = tab;
        loadMarkerStyleToControls(tab);
    }
}

// Update the markers/specials side-panel based on current selection
function updateMarkersPanel() {
    // Update word chips for the active marker tab (highlight or spotlight)
    const chipsContainer = document.getElementById('specials-word-chips');
    const editingLabel = document.getElementById('specials-editing-label');
    const applyAllLabel = document.getElementById('specials-apply-all-label');
    const markerName = currentMarkerTab === 'spotlight' ? 'Spotlight' : 'Highlight';

    if (applyAllLabel) applyAllLabel.textContent = `Apply for all ${markerName.toLowerCase()} words`;

    // Collect all words with the current marker
    const markerWords = [];
    if (subtitleTrack?.segments) {
        subtitleTrack.segments.forEach((seg, segIdx) => {
            (seg.words || []).forEach((word, wordIdx) => {
                if ((word.marker || 'standard') === currentMarkerTab) {
                    markerWords.push({ segIdx, wordIdx, word: word.word });
                }
            });
        });
    }

    if (chipsContainer) {
        if (markerWords.length === 0) {
            chipsContainer.innerHTML = '<span class="text-xs text-slate-400 italic">No words assigned yet</span>';
        } else {
            const chipColor = currentMarkerTab === 'spotlight'
                ? 'bg-purple-900/30 border-purple-500/40 text-purple-200'
                : 'bg-amber-900/30 border-amber-500/40 text-amber-200';
            chipsContainer.innerHTML = markerWords.map(mw =>
                `<span class="text-[11px] px-1.5 py-0.5 rounded border ${chipColor} cursor-pointer hover:opacity-80"
                       data-seg="${mw.segIdx}" data-word="${mw.wordIdx}">${escapeHtml(mw.word)}</span>`
            ).join('');
            // Click chip → select that word + seek
            chipsContainer.querySelectorAll('[data-seg]').forEach(chip => {
                chip.addEventListener('click', () => {
                    const si = parseInt(chip.dataset.seg);
                    const wi = parseInt(chip.dataset.word);
                    selectedWords = [{ segmentIndex: si, wordIndex: wi }];
                    updateWordSelectionUI();
                    updateEditingIndicators();
                    const w = subtitleTrack.segments[si]?.words?.[wi];
                    if (w) document.getElementById('video-player').currentTime = w.start_time;
                });
            });
        }
    }

    // Update editing indicators
    updateEditingIndicators();
}

/**
 * Update the "Editing: ..." label on all three tabs.
 */
function updateEditingIndicators() {
    // Standard tab indicator
    const stdLabel = document.getElementById('standard-editing-label');
    if (stdLabel) {
        if (selectedWords.length > 0) {
            const firstWord = getSelectedWord();
            if (firstWord && (firstWord.marker || 'standard') === 'standard') {
                stdLabel.textContent = `"${firstWord.word}" (segment ${selectedWords[0].segmentIndex + 1})`;
            } else {
                stdLabel.textContent = 'All standard words';
            }
        } else {
            stdLabel.textContent = 'All standard words';
        }
    }

    // Specials (Highlight / Spotlight) tab indicator
    const specLabel = document.getElementById('specials-editing-label');
    if (specLabel) {
        const markerName = currentMarkerTab === 'spotlight' ? 'Spotlight' : 'Highlight';
        if (selectedWords.length > 0) {
            const firstWord = getSelectedWord();
            if (firstWord && (firstWord.marker || 'standard') === currentMarkerTab) {
                specLabel.textContent = `"${firstWord.word}" (${markerName})`;
            } else {
                specLabel.textContent = `All ${markerName.toLowerCase()} words`;
            }
        } else {
            specLabel.textContent = `All ${markerName.toLowerCase()} words`;
        }
    }
}

// Keep backward compat alias
const updateSpecialsPanel = updateMarkersPanel;

/**
 * Load a marker-type style object (highlight / spotlight) into the
 * special-* controls:
 */
function loadMarkerStyleToControls(markerTab) {
    if (!subtitleTrack) return;
    const style = markerTab === 'spotlight'
        ? (subtitleTrack.spotlight_style || subtitleTrack.global_style || {})
        : (subtitleTrack.highlight_style || subtitleTrack.global_style || {});

    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    setVal('special-font', style.font_family || 'Noto Sans Devanagari');
    setVal('special-font-size', style.font_size || 48);
    setText('special-font-size-val', style.font_size || 48);
    setVal('special-font-weight', style.font_weight || 400);
    setText('special-font-weight-val', style.font_weight || 400);
    setVal('special-font-style', style.font_style || 'normal');
    setVal('special-text-transform', style.text_transform || 'none');

    setVal('special-fill-type', style.fill_type || 'solid');
    setVal('special-text-color', style.text_color || '#FFFFFF');
    setVal('special-grad-color1', style.gradient_color1 || '#FFFFFF');
    setVal('special-grad-color2', style.gradient_color2 || '#FFD700');
    setVal('special-grad-angle', style.gradient_angle || 0);
    setText('special-grad-angle-val', `${style.gradient_angle || 0}°`);
    setVal('special-grad-type', style.gradient_type || 'linear');
    toggleFillControls('special', style.fill_type || 'solid');

    const strokeCheck = document.getElementById('special-stroke-enabled');
    if (strokeCheck) strokeCheck.checked = style.stroke_enabled !== false;
    setVal('special-outline-color', style.outline_color || '#000000');
    setVal('special-outline-width', style.outline_width ?? 2);
    setText('special-outline-w-val', style.outline_width ?? 2);
    toggleStrokeControls('special', style.stroke_enabled !== false);

    const shadowCheck = document.getElementById('special-shadow-enabled');
    if (shadowCheck) shadowCheck.checked = style.shadow_enabled !== false;
    setVal('special-shadow-color', (style.shadow_color || '#000000'));
    setVal('special-shadow-blur', style.shadow_blur || 0);
    setText('special-shadow-blur-val', style.shadow_blur || 0);
    setVal('special-shadow-ox', style.shadow_offset_x ?? 2);
    setText('special-shadow-ox-val', style.shadow_offset_x ?? 2);
    setVal('special-shadow-oy', style.shadow_offset_y ?? 2);
    setText('special-shadow-oy-val', style.shadow_offset_y ?? 2);
    toggleShadowControls('special', style.shadow_enabled !== false);

    setVal('special-letter-spacing', style.letter_spacing || 0);
    setText('special-letter-spacing-val', style.letter_spacing || 0);
    setVal('special-line-height', style.line_height || 1.2);
    setText('special-line-height-val', style.line_height || 1.2);

    setVal('special-opacity', Math.round((style.text_opacity ?? 1) * 100));
    setText('special-opacity-val', Math.round((style.text_opacity ?? 1) * 100));
}

// Kept for back-compat (called by old path but not needed with new marker system)
function loadSpecialStyle() { loadMarkerStyleToControls(currentMarkerTab); }

// Get the first selected word object
function getSelectedWord() {
    if (selectedWords.length === 0 || !subtitleTrack) return null;
    const { segmentIndex, wordIndex } = selectedWords[0];
    return subtitleTrack.segments[segmentIndex]?.words?.[wordIndex] ?? null;
}

// Initialize word selection in Segments panel
function initWordSelection() {
    // Event listeners are now attached in attachWordSelectionListeners
    // which is called after populateSegments
}

// Handle word click (select or multi-select)
function handleWordClick(wordEl, isMultiSelect) {
    const segmentIndex = parseInt(wordEl.dataset.segmentIdx);
    const wordIndex = parseInt(wordEl.dataset.wordIdx);

    if (!isMultiSelect) {
        // Single select - clear previous selection
        selectedWords = [{ segmentIndex, wordIndex }];
    } else {
        // Multi-select - toggle selection
        const existingIndex = selectedWords.findIndex(
            w => w.segmentIndex === segmentIndex && w.wordIndex === wordIndex
        );
        if (existingIndex >= 0) {
            selectedWords.splice(existingIndex, 1);
        } else {
            selectedWords.push({ segmentIndex, wordIndex });
        }
    }

    updateWordSelectionUI();

    // Auto-switch to the correct marker tab based on the word's marker
    if (selectedWords.length > 0) {
        const word = subtitleTrack?.segments[segmentIndex]?.words?.[wordIndex];
        if (word) {
            const marker = word.marker || 'standard';
            switchToMarkerTab(marker);
        }
    }

    updateSpecialsPanel();
}

// Update UI to show selected words
function updateWordSelectionUI() {
    // Clear all word selections
    document.querySelectorAll('.word-item').forEach(el => {
        el.classList.remove('bg-yellow-500/30', 'border-yellow-500');
    });

    // Highlight selected words
    selectedWords.forEach(({ segmentIndex, wordIndex }) => {
        const wordEl = document.querySelector(
            `.word-item[data-segment-idx="${segmentIndex}"][data-word-idx="${wordIndex}"]`
        );
        if (wordEl) {
            wordEl.classList.add('bg-yellow-500/30', 'border-yellow-500');
        }
    });

    // Update timeline to highlight special words
    if (timeline) {
        timeline.draw();
    }
}

// Context menu for words — new marker system
function initContextMenu() {
    const bind = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', () => { fn(); hideContextMenu(); }); };

    bind('ctx-mark-highlight',  () => setWordMarker('highlight'));
    bind('ctx-mark-spotlight',  () => setWordMarker('spotlight'));
    bind('ctx-mark-standard',   () => setWordMarker('standard'));
    bind('ctx-make-segment',    () => makeWordSegment());
    // Legacy IDs kept so old HTML still works without a full rebuild
    bind('ctx-mark-special',    () => setWordMarker('highlight'));
    bind('ctx-unmark',          () => setWordMarker('standard'));
    bind('ctx-create-group',    () => setWordMarker('highlight'));
    bind('ctx-remove-group',    () => setWordMarker('standard'));

    document.addEventListener('click', hideContextMenu);
}

function showContextMenu(x, y, wordEl) {
    const menu = document.getElementById('word-context-menu');
    if (!menu) return;

    const segmentIndex = parseInt(wordEl.dataset.segmentIdx);
    const wordIndex = parseInt(wordEl.dataset.wordIdx);

    // Auto-select if not already selected
    if (!selectedWords.some(w => w.segmentIndex === segmentIndex && w.wordIndex === wordIndex)) {
        selectedWords = [{ segmentIndex, wordIndex }];
        updateWordSelectionUI();
    }

    const firstWord = getSelectedWord();
    if (!firstWord) return;

    const marker = firstWord.marker || 'standard';
    const show = (id, visible) => { const el = document.getElementById(id); if (el) el.classList.toggle('hidden', !visible); };
    show('ctx-mark-highlight', marker !== 'highlight');
    show('ctx-mark-spotlight', marker !== 'spotlight');
    show('ctx-mark-standard',  marker !== 'standard');
    show('ctx-make-segment',   true);
    // Legacy IDs
    show('ctx-mark-special',   marker === 'standard');
    show('ctx-unmark',         marker !== 'standard');
    show('ctx-create-group',   false); // deprecated
    show('ctx-remove-group',   false); // deprecated

    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.classList.remove('hidden');
}

function hideContextMenu() {
    document.getElementById('word-context-menu').classList.add('hidden');
}

/**
 * Apply a marker ('standard' | 'highlight' | 'spotlight') to all selected words.
 * Keeps sentence boundaries: a spotlighted word inside a sentence still
 * belongs to that sentence segment — the exporter/preview read the marker.
 */
function setWordMarker(marker) {
    if (!subtitleTrack || selectedWords.length === 0) return;

    selectedWords.forEach(({ segmentIndex, wordIndex }) => {
        const seg = subtitleTrack.segments[segmentIndex];
        if (seg?.words?.[wordIndex]) {
            const word = seg.words[wordIndex];
            word.marker = marker;
            // Clear legacy fields
            word.is_special = (marker !== 'standard');
            word.style_override = null;
        }
    });

    timeline?.draw();
    preview?.setTrack(subtitleTrack);
    updateWordSelectionUI();
    autoSave();
    showToast(`Marked as ${marker}`);
}

/**
 * Split the current segment around the selected word, 
 * turning the word into a 1-word segment.
 */
function makeWordSegment() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    // Sort from back to front so indices don't shift as we insert
    const sorted = [...selectedWords].sort((a, b) => {
        if (a.segmentIndex !== b.segmentIndex) return b.segmentIndex - a.segmentIndex;
        return b.wordIndex - a.wordIndex;
    });

    let modified = false;

    for (const {segmentIndex, wordIndex} of sorted) {
        const seg = subtitleTrack.segments[segmentIndex];
        if (!seg || !seg.words || seg.words.length <= 1) continue; // Already a 1-word segment

        const word = seg.words[wordIndex];
        const beforeWords = seg.words.slice(0, wordIndex);
        const afterWords = seg.words.slice(wordIndex + 1);

        const newSegments = [];
        
        if (beforeWords.length > 0) {
            newSegments.push({
                start: beforeWords[0].start,
                end: beforeWords[beforeWords.length - 1].end,
                text: beforeWords.map(w => w.word).join(' '),
                words: beforeWords
            });
        }
        
        newSegments.push({
            start: word.start,
            end: word.end,
            text: word.word,
            words: [word]
        });

        if (afterWords.length > 0) {
            newSegments.push({
                start: afterWords[0].start,
                end: afterWords[afterWords.length - 1].end,
                text: afterWords.map(w => w.word).join(' '),
                words: afterWords
            });
        }

        subtitleTrack.segments.splice(segmentIndex, 1, ...newSegments);
        modified = true;
    }

    if (modified) {
        selectedWords = [];
        populateSegments(); // Rebuild the segments UI
        timeline?.setTrack(subtitleTrack);
        preview?.setTrack(subtitleTrack);
        autoSave();
        showToast("Words split into individual segments");
    }
}

/**
 * Split the current segment around the selected word, 
 * turning the word into a 1-word segment.
 */
function makeWordSegment() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    // Sort from back to front so indices don't shift as we insert
    const sorted = [...selectedWords].sort((a, b) => {
        if (a.segmentIndex !== b.segmentIndex) return b.segmentIndex - a.segmentIndex;
        return b.wordIndex - a.wordIndex;
    });

    let modified = false;

    for (const {segmentIndex, wordIndex} of sorted) {
        const seg = subtitleTrack.segments[segmentIndex];
        if (!seg || !seg.words || seg.words.length <= 1) continue; // Already a 1-word segment

        const word = seg.words[wordIndex];
        const beforeWords = seg.words.slice(0, wordIndex);
        const afterWords = seg.words.slice(wordIndex + 1);

        const newSegments = [];
        
        if (beforeWords.length > 0) {
            newSegments.push({
                start: beforeWords[0].start_time,
                end: beforeWords[beforeWords.length - 1].end_time,
                text: beforeWords.map(w => w.word).join(' '),
                words: beforeWords
            });
        }
        
        newSegments.push({
            start: word.start_time,
            end: word.end_time,
            text: word.word,
            words: [word]
        });

        if (afterWords.length > 0) {
            newSegments.push({
                start: afterWords[0].start_time,
                end: afterWords[afterWords.length - 1].end_time,
                text: afterWords.map(w => w.word).join(' '),
                words: afterWords
            });
        }

        subtitleTrack.segments.splice(segmentIndex, 1, ...newSegments);
        modified = true;
    }

    if (modified) {
        selectedWords = [];
        populateSegments(subtitleTrack.segments);
        timeline?.setData(subtitleTrack, project.video_duration, project.id);
        preview?.setTrack(subtitleTrack);
        autoSave();
        showToast("Words split into individual segments");
    }
}

// Initialize marker style controls (Highlight / Spotlight tabs)
function initMarkerStyleControls() {
    const bindSpecial = (id, prop, parse) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', (e) => {
            const raw = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
            const val = parse ? parse(raw) : raw;
            updateMarkerStyle(prop, val);
        });
    };
    const bindWithVal = (id, valId, prop, parse) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('input', (e) => {
            const el2 = document.getElementById(valId);
            if (el2) el2.textContent = e.target.value + (prop.includes('opacity') ? '' : prop.includes('angle') ? '°' : '');
            updateMarkerStyle(prop, parse ? parse(e.target.value) : e.target.value);
        });
    };

    bindSpecial('special-font', 'font_family', null);
    bindWithVal('special-font-size',   'special-font-size-val',   'font_size',   parseInt);
    bindWithVal('special-font-weight', 'special-font-weight-val', 'font_weight', parseInt);
    bindSpecial('special-font-style',  'font_style', null);
    bindSpecial('special-text-transform', 'text_transform', null);

    const fillTypeEl = document.getElementById('special-fill-type');
    if (fillTypeEl) fillTypeEl.addEventListener('change', (e) => { updateMarkerStyle('fill_type', e.target.value); toggleFillControls('special', e.target.value); });
    bindSpecial('special-text-color',  'text_color', null);
    bindSpecial('special-grad-color1', 'gradient_color1', null);
    bindSpecial('special-grad-color2', 'gradient_color2', null);
    bindWithVal('special-grad-angle',  'special-grad-angle-val', 'gradient_angle', parseInt);
    bindSpecial('special-grad-type',   'gradient_type', null);

    const strokeChk = document.getElementById('special-stroke-enabled');
    if (strokeChk) strokeChk.addEventListener('change', (e) => { updateMarkerStyle('stroke_enabled', e.target.checked); toggleStrokeControls('special', e.target.checked); });
    bindSpecial('special-outline-color', 'outline_color', null);
    bindWithVal('special-outline-width', 'special-outline-w-val', 'outline_width', parseInt);

    const shadowChk = document.getElementById('special-shadow-enabled');
    if (shadowChk) shadowChk.addEventListener('change', (e) => { updateMarkerStyle('shadow_enabled', e.target.checked); toggleShadowControls('special', e.target.checked); });
    bindSpecial('special-shadow-color',  'shadow_color', null);
    bindWithVal('special-shadow-blur',   'special-shadow-blur-val', 'shadow_blur', parseInt);
    bindWithVal('special-shadow-ox',     'special-shadow-ox-val',   'shadow_offset_x', parseInt);
    bindWithVal('special-shadow-oy',     'special-shadow-oy-val',   'shadow_offset_y', parseInt);

    bindWithVal('special-letter-spacing', 'special-letter-spacing-val', 'letter_spacing', parseFloat);
    bindWithVal('special-line-height',    'special-line-height-val',    'line_height',    parseFloat);
    const opacEl = document.getElementById('special-opacity');
    if (opacEl) opacEl.addEventListener('input', (e) => {
        const valEl = document.getElementById('special-opacity-val');
        if (valEl) valEl.textContent = e.target.value;
        updateMarkerStyle('text_opacity', parseInt(e.target.value) / 100);
    });
}

/**
 * Update the style object for the current marker tab (highlight or spotlight).
 * Changes are stored in subtitleTrack.highlight_style / subtitleTrack.spotlight_style.
 */
function updateMarkerStyle(property, value) {
    if (!subtitleTrack) return;

    const key = currentMarkerTab === 'spotlight' ? 'spotlight_style' : 'highlight_style';
    if (!subtitleTrack[key]) subtitleTrack[key] = {};
    subtitleTrack[key][property] = value;

    preview?.setTrack(subtitleTrack);
    timeline?.draw();
    autoSave();
}

// Alias kept for old code paths
const updateSpecialStyle = updateMarkerStyle;

// Initialize global style controls
function initGlobalStyleControls() {
    // §1 Font
    document.getElementById('global-font').addEventListener('change', (e) => {
        updateGlobalStyle('font_family', e.target.value);
    });
    document.getElementById('global-font-size').addEventListener('input', (e) => {
        document.getElementById('global-font-size-val').textContent = e.target.value;
        updateGlobalStyle('font_size', parseInt(e.target.value));
    });
    document.getElementById('global-font-weight').addEventListener('input', (e) => {
        document.getElementById('global-font-weight-val').textContent = e.target.value;
        updateGlobalStyle('font_weight', parseInt(e.target.value));
    });
    document.getElementById('global-font-style').addEventListener('change', (e) => {
        updateGlobalStyle('font_style', e.target.value);
    });
    document.getElementById('global-text-transform').addEventListener('change', (e) => {
        updateGlobalStyle('text_transform', e.target.value);
    });

    // §2 Fill
    document.getElementById('global-fill-type').addEventListener('change', (e) => {
        updateGlobalStyle('fill_type', e.target.value);
        toggleFillControls('global', e.target.value);
    });
    document.getElementById('global-text-color').addEventListener('input', (e) => {
        updateGlobalStyle('text_color', e.target.value);
    });
    document.getElementById('global-grad-color1').addEventListener('input', (e) => {
        updateGlobalStyle('gradient_color1', e.target.value);
    });
    document.getElementById('global-grad-color2').addEventListener('input', (e) => {
        updateGlobalStyle('gradient_color2', e.target.value);
    });
    document.getElementById('global-grad-angle').addEventListener('input', (e) => {
        document.getElementById('global-grad-angle-val').textContent = `${e.target.value}°`;
        updateGlobalStyle('gradient_angle', parseInt(e.target.value));
    });
    document.getElementById('global-grad-type').addEventListener('change', (e) => {
        updateGlobalStyle('gradient_type', e.target.value);
    });

    // §3 Stroke
    document.getElementById('global-stroke-enabled').addEventListener('change', (e) => {
        updateGlobalStyle('stroke_enabled', e.target.checked);
        toggleStrokeControls('global', e.target.checked);
    });
    document.getElementById('global-outline-color').addEventListener('input', (e) => {
        updateGlobalStyle('outline_color', e.target.value);
    });
    document.getElementById('global-outline-width').addEventListener('input', (e) => {
        document.getElementById('global-outline-w-val').textContent = e.target.value;
        updateGlobalStyle('outline_width', parseInt(e.target.value));
    });

    // §4 Shadow
    document.getElementById('global-shadow-enabled').addEventListener('change', (e) => {
        updateGlobalStyle('shadow_enabled', e.target.checked);
        toggleShadowControls('global', e.target.checked);
    });
    document.getElementById('global-shadow-color').addEventListener('input', (e) => {
        updateGlobalStyle('shadow_color', e.target.value);
    });
    document.getElementById('global-shadow-blur').addEventListener('input', (e) => {
        document.getElementById('global-shadow-blur-val').textContent = e.target.value;
        updateGlobalStyle('shadow_blur', parseInt(e.target.value));
    });
    document.getElementById('global-shadow-ox').addEventListener('input', (e) => {
        document.getElementById('global-shadow-ox-val').textContent = e.target.value;
        updateGlobalStyle('shadow_offset_x', parseInt(e.target.value));
    });
    document.getElementById('global-shadow-oy').addEventListener('input', (e) => {
        document.getElementById('global-shadow-oy-val').textContent = e.target.value;
        updateGlobalStyle('shadow_offset_y', parseInt(e.target.value));
    });

    // §5 Spacing
    document.getElementById('global-letter-spacing').addEventListener('input', (e) => {
        document.getElementById('global-letter-spacing-val').textContent = e.target.value;
        updateGlobalStyle('letter_spacing', parseFloat(e.target.value));
    });
    document.getElementById('global-word-spacing').addEventListener('input', (e) => {
        document.getElementById('global-word-spacing-val').textContent = e.target.value;
        updateGlobalStyle('word_spacing', parseFloat(e.target.value));
    });
    document.getElementById('global-line-height').addEventListener('input', (e) => {
        document.getElementById('global-line-height-val').textContent = e.target.value;
        updateGlobalStyle('line_height', parseFloat(e.target.value));
    });

    // §6 Opacity
    document.getElementById('global-opacity').addEventListener('input', (e) => {
        document.getElementById('global-opacity-val').textContent = e.target.value;
        updateGlobalStyle('text_opacity', parseInt(e.target.value) / 100);
    });

    // Video tab controls
    document.getElementById('global-vid-rotation').addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        document.getElementById('global-vid-rot-val').textContent = `${value}°`;
        document.getElementById('global-vid-rotation-input').value = value;
        if (subtitleTrack) {
            subtitleTrack.video_rotation = value;
            const video = document.getElementById('video-player');
            if (video) video.style.transform = `rotate(${value}deg)`;
            autoSave();
        }
    });
    document.getElementById('global-vid-rotation-input').addEventListener('input', (e) => {
        let value = parseInt(e.target.value);
        // Validate and clamp value
        if (isNaN(value)) value = 0;
        value = Math.max(-180, Math.min(180, value));
        e.target.value = value;
        document.getElementById('global-vid-rotation').value = value;
        document.getElementById('global-vid-rot-val').textContent = `${value}°`;
        if (subtitleTrack) {
            subtitleTrack.video_rotation = value;
            const video = document.getElementById('video-player');
            if (video) video.style.transform = `rotate(${value}deg)`;
            autoSave();
        }
    });
    document.getElementById('global-sub-rotation').addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        document.getElementById('global-sub-rot-val').textContent = `${value}°`;
        document.getElementById('global-sub-rotation-input').value = value;
        updateGlobalStyle('rotation', value);
    });
    document.getElementById('global-sub-rotation-input').addEventListener('input', (e) => {
        let value = parseInt(e.target.value);
        // Validate and clamp value
        if (isNaN(value)) value = 0;
        value = Math.max(-180, Math.min(180, value));
        e.target.value = value;
        document.getElementById('global-sub-rotation').value = value;
        document.getElementById('global-sub-rot-val').textContent = `${value}°`;
        updateGlobalStyle('rotation', value);
    });
    const wplEl = document.getElementById('global-wpl');
    if (wplEl) {
        wplEl.addEventListener('input', (e) => {
            document.getElementById('global-wpl-val').textContent = e.target.value;
            if (!subtitleTrack || subtitleTrack.sentence_mode) return; // Disabled in sentence mode
            subtitleTrack.words_per_line = parseInt(e.target.value);
            const allWords = [];
            for (const seg of subtitleTrack.segments) allWords.push(...seg.words);
            subtitleTrack.segments = [];
            for (let i = 0; i < allWords.length; i += subtitleTrack.words_per_line) {
                const chunk = allWords.slice(i, i + subtitleTrack.words_per_line);
                subtitleTrack.segments.push({ words: chunk, style: { ...subtitleTrack.global_style } });
            }
            populateSegments(subtitleTrack.segments);
            populateFullText(subtitleTrack.segments);
            preview?.setTrack(subtitleTrack);
            timeline?.setData(subtitleTrack, project.video_duration, project.id);
            autoSave();
        });
    }

    // Text box width
    const tbwEl = document.getElementById('global-text-box-width');
    if (tbwEl) {
        tbwEl.addEventListener('input', (e) => {
            const valEl = document.getElementById('global-text-box-width-val');
            if (valEl) valEl.textContent = `${e.target.value}%`;
            if (subtitleTrack) {
                subtitleTrack.text_box_width = parseInt(e.target.value) / 100;
                preview?.setTrack(subtitleTrack);
                autoSave();
            }
        });
    }

    // Animation controls
    document.getElementById('global-animation').addEventListener('change', (e) => {
        if (subtitleTrack) {
            subtitleTrack.animation_type = e.target.value;
            preview?.setTrack(subtitleTrack);
            autoSave();
        }
    });
    document.getElementById('global-anim-duration').addEventListener('input', (e) => {
        document.getElementById('global-anim-dur-val').textContent = `${e.target.value}s`;
        if (subtitleTrack) {
            subtitleTrack.animation_duration = parseFloat(e.target.value);
            preview?.setTrack(subtitleTrack);
            autoSave();
        }
    });
}

// Update global style
function updateGlobalStyle(property, value) {
    if (!subtitleTrack) return;

    // Update global style
    if (subtitleTrack.global_style) {
        subtitleTrack.global_style[property] = value;
    }

    // Update all segment styles
    if (subtitleTrack.segments) {
        for (const seg of subtitleTrack.segments) {
            if (seg.style) {
                seg.style[property] = value;
            }
        }
    }

    preview?.setTrack(subtitleTrack);
    autoSave();
}

// Deselect on Escape key or clicking elsewhere
function initDeselectOnEscape() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            selectedWords = [];
            updateWordSelectionUI();
            updateSpecialsPanel();
        }
    });

    document.addEventListener('click', (e) => {
        // Don't deselect if clicking on a word item or context menu
        if (e.target.closest('.word-item') || e.target.closest('#word-context-menu')) {
            return;
        }
        // Don't deselect if clicking on style controls (All or Specials subsections)
        if (e.target.closest('#all-subsection') || e.target.closest('#specials-subsection')) {
            return;
        }
        // Don't deselect if clicking on subsection tabs
        if (e.target.closest('[data-sub-tab]')) {
            return;
        }
        // Don't deselect if clicking on main tabs
        if (e.target.closest('[data-main-tab]')) {
            return;
        }
        // Deselect when clicking elsewhere
        selectedWords = [];
        updateWordSelectionUI();
        updateSpecialsPanel();
    });
}

/**
 * Marker colour for word chips in the segments panel.
 * Standard → no colour; Highlight → amber; Spotlight → purple
 */
function markerChipColor(marker) {
    switch (marker) {
        case 'highlight': return 'background:rgba(255,200,0,0.18);border:1px solid rgba(255,200,0,0.5);';
        case 'spotlight': return 'background:rgba(180,80,255,0.18);border:1px solid rgba(180,80,255,0.5);';
        default: return '';
    }
}

// Override populateSegments to show word selections with new marker colours
const _origPopulateSegments = populateSegments;
populateSegments = function(segments) {
    const panel = document.getElementById('segments-panel');
    if (!panel) return;

    if (!segments || segments.length === 0) {
        panel.innerHTML = '<p class="text-sm text-slate-400">No transcript segments.</p>';
        return;
    }

    panel.innerHTML = segments.map((seg, segIdx) => {
        const startTime = seg.words?.[0]?.start_time || 0;
        const endTime = seg.words?.[seg.words.length - 1]?.end_time || 0;

        const wordsHtml = (seg.words || []).map((word, wordIdx) => {
            const marker = word.marker || 'standard';
            const chipStyle = markerChipColor(marker);
            return `<span class="word-item px-1 py-0.5 rounded cursor-pointer hover:bg-white/10 transition-colors" style="${chipStyle}" data-segment-idx="${segIdx}" data-word-idx="${wordIdx}" title="${marker}">${escapeHtml(word.word)}</span>`;
        }).join(' ');

        return `
            <div class="segment-item p-2 rounded-lg border border-transparent hover:border-white/10 hover:bg-white/5 cursor-pointer transition-all" data-idx="${segIdx}">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-[10px] text-primary font-mono">${formatDuration(startTime)}</span>
                    <span class="text-[10px] text-slate-500">→</span>
                    <span class="text-[10px] text-primary font-mono">${formatDuration(endTime)}</span>
                </div>
                <p class="text-sm text-slate-200 leading-relaxed flex flex-wrap gap-y-1">${wordsHtml}</p>
            </div>`;
    }).join('');

    // Segment click — seek
    panel.querySelectorAll('.segment-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.word-item')) return;
            const idx = parseInt(item.dataset.idx);
            const seg = segments[idx];
            document.getElementById('video-player').currentTime = seg.words?.[0]?.start_time || 0;
            if (timeline) { timeline.selectedIndex = { track: 'text', index: idx }; timeline.draw(); }
            highlightSegment(idx);
        });
    });

    updateWordSelectionUI();
    attachWordSelectionListeners();
};

// Attach word selection listeners (clone to remove old ones)
function attachWordSelectionListeners() {
    const panel = document.getElementById('segments-panel');
    if (!panel) return;

    const newPanel = panel.cloneNode(true);
    panel.parentNode.replaceChild(newPanel, panel);

    // Delegated segment-level click (seek + highlight)
    newPanel.addEventListener('click', (e) => {
        // If a word was clicked, handle word selection instead
        const wordEl = e.target.closest('.word-item');
        if (wordEl) {
            e.stopPropagation();
            handleWordClick(wordEl, e.ctrlKey || e.metaKey);
            return;
        }
        // Segment-level click — seek to segment start
        const segItem = e.target.closest('.segment-item');
        if (segItem) {
            const idx = parseInt(segItem.dataset.idx);
            const seg = subtitleTrack?.segments?.[idx];
            if (seg) {
                document.getElementById('video-player').currentTime = seg.words?.[0]?.start_time || 0;
                if (timeline) { timeline.selectedIndex = { track: 'text', index: idx }; timeline.draw(); }
                highlightSegment(idx);
            }
        }
    });

    newPanel.addEventListener('contextmenu', (e) => {
        const wordEl = e.target.closest('.word-item');
        if (!wordEl) return;
        e.preventDefault();
        showContextMenu(e.clientX, e.clientY, wordEl);
    });
}
