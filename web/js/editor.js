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
    initStylingSystem();  // Replaces initStyleControls and initTabSwitching
    initFullTextEditing();
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

// Ensure subtitleTrack has all necessary methods (for JSON-loaded data)
function ensureSubtitleTrackMethods() {
    if (!subtitleTrack) return;

    // Ensure special_groups exists
    if (!subtitleTrack.special_groups) {
        subtitleTrack.special_groups = {};
    }

    // Add create_group method if missing
    if (!subtitleTrack.create_group) {
        subtitleTrack.create_group = function(name = "") {
            const groupId = 'group_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            this.special_groups[groupId] = {
                id: groupId,
                name: name,
                style: this.global_style ? JSON.parse(JSON.stringify(this.global_style)) : {}
            };
            return groupId;
        };
    }

    // Add delete_group method if missing
    if (!subtitleTrack.delete_group) {
        subtitleTrack.delete_group = function(groupId) {
            if (this.special_groups && this.special_groups[groupId]) {
                delete this.special_groups[groupId];
                // Remove group_id from all words
                if (this.segments) {
                    for (const seg of this.segments) {
                        if (seg.words) {
                            for (const word of seg.words) {
                                if (word.group_id === groupId) {
                                    word.group_id = null;
                                    word.is_special = false;
                                }
                            }
                        }
                    }
                }
            }
        };
    }

    // Add get_group_style method if missing
    if (!subtitleTrack.get_group_style) {
        subtitleTrack.get_group_style = function(groupId) {
            const group = this.special_groups && this.special_groups[groupId];
            return group ? group.style : null;
        };
    }

    // Add get_group_members method if missing
    if (!subtitleTrack.get_group_members) {
        subtitleTrack.get_group_members = function(groupId) {
            const members = [];
            if (this.segments) {
                for (let segIdx = 0; segIdx < this.segments.length; segIdx++) {
                    const seg = this.segments[segIdx];
                    if (seg.words) {
                        for (let wordIdx = 0; wordIdx < seg.words.length; wordIdx++) {
                            const word = seg.words[wordIdx];
                            if (word.group_id === groupId) {
                                members.push([segIdx, wordIdx]);
                            }
                        }
                    }
                }
            }
            return members;
        };
    }

    // Ensure global_style has copy method
    if (subtitleTrack.global_style && !subtitleTrack.global_style.copy) {
        subtitleTrack.global_style.copy = function() {
            return JSON.parse(JSON.stringify(this));
        };
    }

    // Ensure all segment styles have copy method
    if (subtitleTrack.segments) {
        for (const seg of subtitleTrack.segments) {
            if (seg.style && !seg.style.copy) {
                seg.style.copy = function() {
                    return JSON.parse(JSON.stringify(this));
                };
            }
        }
    }
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
}

function populateFullText(segments) {
    const textarea = document.getElementById('fulltext-area');
    if (!segments) return;
    const allText = segments.map(seg => seg.words?.map(w => w.word).join(' ') || '').join('\n');
    textarea.value = allText;
}

function initFullTextEditing() {
    const textarea = document.getElementById('fulltext-area');
    if (!textarea) return;

    textarea.addEventListener('input', () => {
        if (!subtitleTrack || !subtitleTrack.segments) return;

        // Split by newlines to get lines (keep empty lines to preserve segment count)
        const lines = textarea.value.split('\n');

        // Update segments with new text
        const newSegments = [];
        for (let i = 0; i < Math.max(lines.length, subtitleTrack.segments.length); i++) {
            const oldSeg = subtitleTrack.segments[i];
            const lineText = lines[i] || '';

            if (oldSeg && oldSeg.words && oldSeg.words.length > 0) {
                // Split line into words and update existing word timings
                const newWords = lineText.trim().split(/\s+/).filter(w => w !== '');
                const updatedWords = [];

                if (newWords.length > 0) {
                    for (let j = 0; j < newWords.length; j++) {
                        const oldWord = oldSeg.words[j];
                        if (oldWord) {
                            // Preserve timing from old word
                            updatedWords.push({
                                word: newWords[j],
                                start_time: oldWord.start_time,
                                end_time: oldWord.end_time,
                                confidence: oldWord.confidence || 1.0
                            });
                        } else {
                            // New word - estimate timing
                            const lastWord = updatedWords[updatedWords.length - 1];
                            const startTime = lastWord ? lastWord.end_time : (oldSeg.words[0]?.start_time || 0);
                            const duration = 0.5; // Default duration
                            updatedWords.push({
                                word: newWords[j],
                                start_time: startTime,
                                end_time: startTime + duration,
                                confidence: 1.0
                            });
                        }
                    }

                    newSegments.push({
                        words: updatedWords,
                        style: oldSeg.style || {}
                    });
                }
                // If newWords is empty, we skip this segment (effectively deleting it)
            } else if (lineText.trim()) {
                // New segment - create with default timing
                const words = lineText.trim().split(/\s+/).map((w, idx) => ({
                    word: w,
                    start_time: idx * 0.5,
                    end_time: (idx + 1) * 0.5,
                    confidence: 1.0
                }));
                newSegments.push({
                    words: words,
                    style: subtitleTrack.global_style || {}
                });
            }
        }

        // Update subtitle track
        subtitleTrack.segments = newSegments;

        // Update UI
        populateSegments(newSegments);
        preview?.setTrack(subtitleTrack);
        timeline?.setData(subtitleTrack, project.video_duration, project.id);

        // Auto-save
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
    // Load templates into all template panels
    const templatePanels = [
        document.getElementById('all-templates-panel'),
        document.getElementById('specials-templates-panel'),
        document.getElementById('presets-templates-panel')
    ].filter(p => p !== null);  // Filter out null panels

    if (templatePanels.length === 0) {
        console.warn('[loadPresets] No template panels found');
        return;
    }

    try {
        const presets = await getPresets();
        if (!presets.length) {
            templatePanels.forEach(panel => {
                panel.innerHTML = '<p class="text-sm text-slate-400">No presets available.</p>';
            });
            return;
        }

        const templateHtml = presets.map((preset, idx) => `
            <div class="preset-card p-3 rounded-lg border border-white/10 bg-white/5 cursor-pointer hover:border-primary/30 transition-all" data-idx="${idx}">
                <div class="text-sm font-bold text-white mb-1">${escapeHtml(preset.name)}</div>
                <div class="text-xs text-slate-400">${escapeHtml(preset.description || '')}</div>
                <div class="mt-2 text-lg font-bold" style="color: ${preset.style?.text_color || '#fff'}; text-shadow: 1px 1px 2px ${preset.style?.outline_color || '#000'};">
                    Sample सैम्पल
                </div>
            </div>
        `).join('');

        templatePanels.forEach(panel => {
            panel.innerHTML = templateHtml;

            panel.querySelectorAll('.preset-card').forEach(card => {
                card.addEventListener('click', () => {
                    const idx = parseInt(card.dataset.idx);
                    const preset = presets[idx];
                    if (preset.style && subtitleTrack) {
                        // Apply preset style
                        subtitleTrack.global_style = { ...subtitleTrack.global_style, ...preset.style };
                        if (subtitleTrack.segments) {
                            for (const seg of subtitleTrack.segments) {
                                if (seg.style) {
                                    seg.style = { ...seg.style, ...preset.style };
                                }
                            }
                        }
                        preview?.setTrack(subtitleTrack);
                        applyTrackToControls(subtitleTrack);
                        autoSave();
                        showToast(`Applied "${preset.name}" style`);
                    }
                });
            });
        });
    } catch (err) {
        console.error('Failed to load presets:', err);
        templatePanels.forEach(panel => {
            panel.innerHTML = '<p class="text-sm text-red-400">Error loading presets.</p>';
        });
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

    // Words per line slider
    const wplSlider = document.getElementById('transcribe-wpl');
    const wplVal = document.getElementById('transcribe-wpl-val');
    if (wplSlider && wplVal) {
        wplSlider.addEventListener('input', () => {
            wplVal.textContent = wplSlider.value;
        });
    }

    btnTranscribe.addEventListener('click', () => showModal(modal));
    btnCancel.addEventListener('click', () => hideModal(modal));

    btnStart.addEventListener('click', async () => {
        const engine = document.getElementById('transcribe-engine')?.value || 'vosk';
        const model = (engine === 'whisper') ? (document.getElementById('transcribe-model')?.value || null) : null;
        const language = project?.language || 'hi';
        const wordsPerLine = parseInt(document.getElementById('transcribe-wpl')?.value || '4');

        const progressWrap = document.getElementById('transcribe-progress-wrap');
        const statusEl = document.getElementById('transcribe-status');
        const barEl = document.getElementById('transcribe-progress-bar');
        const buttons = document.getElementById('transcribe-buttons');

        progressWrap.classList.remove('hidden');
        buttons.classList.add('hidden');

        try {
            const { task_id } = await startTranscription(project.id, { engine, language, model, words_per_line: wordsPerLine });

            watchProgress(task_id,
                (data) => {
                    console.log('[Transcription] Progress:', data);
                    barEl.style.width = `${data.percent}%`;
                    statusEl.textContent = data.message;
                },
                (data) => {
                    console.log('[Transcription] Complete:', data);
                    progressWrap.classList.add('hidden');
                    buttons.classList.remove('hidden');
                    hideModal(modal);
                    showToast('Transcription complete!');
                    // Reload project to get subtitle data (with small delay for DB commit)
                    setTimeout(() => loadProject(project.id), 500);
                },
                (error) => {
                    console.error('[Transcription] Error:', error);
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


// ── Special Words & Groups System ─────────────────────────────────────────────

// Track selected words: array of {segmentIndex, wordIndex}
let selectedWords = [];
let currentGroupId = null;  // Currently selected group

// Initialize the new styling system
function initStylingSystem() {
    initTabSwitching(); // Left panel tabs (Segments / Full Text)
    initMainTabSwitching();
    initSubTabSwitching();
    initContextMenu();
    initSpecialStyleControls();
    initGlobalStyleControls();
    initDeselectOnEscape();
}

// Main tab switching (Style / Video / Presets)
function initMainTabSwitching() {
    document.querySelectorAll('[data-main-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-main-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.mainTab;
            document.getElementById('style-section').classList.toggle('hidden', tab !== 'style');
            document.getElementById('video-section').classList.toggle('hidden', tab !== 'video');
            document.getElementById('presets-section').classList.toggle('hidden', tab !== 'presets');
        });
    });
}

// Sub tab switching (All / Specials)
function initSubTabSwitching() {
    document.querySelectorAll('[data-sub-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-sub-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.subTab;
            document.getElementById('all-subsection').classList.toggle('hidden', tab !== 'all');
            document.getElementById('specials-subsection').classList.toggle('hidden', tab !== 'specials');

            // Update specials panel based on selection
            updateSpecialsPanel();
        });
    });

    // All subsection tabs
    document.querySelectorAll('[data-all-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-all-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.allTab;
            document.getElementById('all-text-panel').classList.toggle('hidden', tab !== 'text');
            document.getElementById('all-templates-panel').classList.toggle('hidden', tab !== 'templates');
            document.getElementById('all-animation-panel').classList.toggle('hidden', tab !== 'animation');
        });
    });

    // Specials subsection tabs
    document.querySelectorAll('[data-special-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-special-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.specialTab;
            document.getElementById('specials-text-panel').classList.toggle('hidden', tab !== 'text');
            document.getElementById('specials-templates-panel').classList.toggle('hidden', tab !== 'templates');
            document.getElementById('specials-animation-panel').classList.toggle('hidden', tab !== 'animation');
        });
    });

    // Presets section tabs
    document.querySelectorAll('[data-preset-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-preset-tab]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.presetTab;
            document.getElementById('presets-panel').classList.toggle('hidden', tab !== 'presets');
            document.getElementById('presets-templates-panel').classList.toggle('hidden', tab !== 'templates');
        });
    });
}

// Update the specials panel based on current selection
function updateSpecialsPanel() {
    const emptyState = document.getElementById('specials-empty');
    const textPanel = document.getElementById('specials-text-panel');
    const templatesPanel = document.getElementById('specials-templates-panel');
    const animationPanel = document.getElementById('specials-animation-panel');

    if (selectedWords.length === 0) {
        emptyState.classList.remove('hidden');
        textPanel.classList.add('hidden');
        templatesPanel.classList.add('hidden');
        animationPanel.classList.add('hidden');
    } else {
        emptyState.classList.add('hidden');
        // Show the active tab panel
        const activeTab = document.querySelector('[data-special-tab].active')?.dataset.specialTab || 'text';
        textPanel.classList.toggle('hidden', activeTab !== 'text');
        templatesPanel.classList.toggle('hidden', activeTab !== 'templates');
        animationPanel.classList.toggle('hidden', activeTab !== 'animation');

        // Load the style for the selected words
        loadSpecialStyle();
    }
}

// Load special style into the controls
function loadSpecialStyle() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    // Get the first selected word's style
    const firstWord = getSelectedWord();
    if (!firstWord) return;

    // Check if word has individual style override
    let style = firstWord.style_override;

    // If no individual style, check if it's in a group
    if (!style && firstWord.group_id) {
        style = subtitleTrack.get_group_style(firstWord.group_id);
    }

    // If still no style, use global style as default
    if (!style) {
        style = subtitleTrack.global_style;
    }

    if (!style) return;

    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    // §1 Font
    setVal('special-font', style.font_family || 'Noto Sans Devanagari');
    setVal('special-font-size', style.font_size || 48);
    setText('special-font-size-val', style.font_size || 48);
    setVal('special-font-weight', style.font_weight || 400);
    setText('special-font-weight-val', style.font_weight || 400);
    setVal('special-font-style', style.font_style || 'normal');
    setVal('special-text-transform', style.text_transform || 'none');

    // §2 Fill
    setVal('special-fill-type', style.fill_type || 'solid');
    setVal('special-text-color', style.text_color || '#FFFFFF');
    setVal('special-grad-color1', style.gradient_color1 || '#FFFFFF');
    setVal('special-grad-color2', style.gradient_color2 || '#FFD700');
    setVal('special-grad-angle', style.gradient_angle || 0);
    setText('special-grad-angle-val', `${style.gradient_angle || 0}°`);
    setVal('special-grad-type', style.gradient_type || 'linear');
    toggleFillControls('special', style.fill_type || 'solid');

    // §3 Stroke
    const strokeCheck = document.getElementById('special-stroke-enabled');
    if (strokeCheck) strokeCheck.checked = style.stroke_enabled !== false;
    setVal('special-outline-color', style.outline_color || '#000000');
    setVal('special-outline-width', style.outline_width || 2);
    setText('special-outline-w-val', style.outline_width || 2);
    toggleStrokeControls('special', style.stroke_enabled !== false);

    // §4 Shadow
    const shadowCheck = document.getElementById('special-shadow-enabled');
    if (shadowCheck) shadowCheck.checked = style.shadow_enabled !== false;
    setVal('special-shadow-color', (style.shadow_color || '#000000').replace(/^#../, '#'));
    setVal('special-shadow-blur', style.shadow_blur || 0);
    setText('special-shadow-blur-val', style.shadow_blur || 0);
    setVal('special-shadow-ox', style.shadow_offset_x ?? 2);
    setText('special-shadow-ox-val', style.shadow_offset_x ?? 2);
    setVal('special-shadow-oy', style.shadow_offset_y ?? 2);
    setText('special-shadow-oy-val', style.shadow_offset_y ?? 2);
    toggleShadowControls('special', style.shadow_enabled !== false);

    // §5 Spacing
    setVal('special-letter-spacing', style.letter_spacing || 0);
    setText('special-letter-spacing-val', style.letter_spacing || 0);
    setVal('special-word-spacing', style.word_spacing || 0);
    setText('special-word-spacing-val', style.word_spacing || 0);
    setVal('special-line-height', style.line_height || 1.2);
    setText('special-line-height-val', style.line_height || 1.2);

    // §6 Opacity
    setVal('special-opacity', Math.round((style.text_opacity ?? 1) * 100));
    setText('special-opacity-val', Math.round((style.text_opacity ?? 1) * 100));
}

// Get the first selected word object
function getSelectedWord() {
    if (selectedWords.length === 0 || !subtitleTrack) return null;
    const { segmentIndex, wordIndex } = selectedWords[0];
    const segment = subtitleTrack.segments[segmentIndex];
    return segment?.words[wordIndex];
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

    console.log('[handleWordClick] segmentIndex:', segmentIndex, 'wordIndex:', wordIndex, 'isMultiSelect:', isMultiSelect);

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

    console.log('[handleWordClick] selectedWords:', selectedWords);
    updateWordSelectionUI();
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

// Context menu for words
function initContextMenu() {
    const menu = document.getElementById('word-context-menu');

    // Mark as Special
    document.getElementById('ctx-mark-special').addEventListener('click', () => {
        markWordsAsSpecial();
        hideContextMenu();
    });

    // Unmark
    document.getElementById('ctx-unmark').addEventListener('click', () => {
        unmarkWords();
        hideContextMenu();
    });

    // Create Group
    document.getElementById('ctx-create-group').addEventListener('click', () => {
        createGroup();
        hideContextMenu();
    });

    // Remove from Group
    document.getElementById('ctx-remove-group').addEventListener('click', () => {
        removeFromGroup();
        hideContextMenu();
    });

    // Hide menu on click elsewhere
    document.addEventListener('click', () => {
        hideContextMenu();
    });
}

function showContextMenu(x, y, wordEl) {
    const menu = document.getElementById('word-context-menu');
    const segmentIndex = parseInt(wordEl.dataset.segmentIdx);
    const wordIndex = parseInt(wordEl.dataset.wordIdx);

    // Check if this word is selected
    const isSelected = selectedWords.some(
        w => w.segmentIndex === segmentIndex && w.wordIndex === wordIndex
    );

    // If not selected, select it first
    if (!isSelected) {
        selectedWords = [{ segmentIndex, wordIndex }];
        updateWordSelectionUI();
    }

    // Get the first selected word
    const firstWord = getSelectedWord();
    if (!firstWord) return;

    // Update menu items based on state
    const isSpecial = firstWord.is_special;
    const hasGroup = !!firstWord.group_id;

    document.getElementById('ctx-mark-special').classList.toggle('hidden', isSpecial);
    document.getElementById('ctx-unmark').classList.toggle('hidden', !isSpecial);
    document.getElementById('ctx-create-group').classList.toggle('hidden', selectedWords.length < 2 || hasGroup);
    document.getElementById('ctx-remove-group').classList.toggle('hidden', !hasGroup);

    // Position menu
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.classList.remove('hidden');
}

function hideContextMenu() {
    document.getElementById('word-context-menu').classList.add('hidden');
}

// Mark selected words as special
function markWordsAsSpecial() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    selectedWords.forEach(({ segmentIndex, wordIndex }) => {
        const segment = subtitleTrack.segments[segmentIndex];
        if (segment && segment.words[wordIndex]) {
            const word = segment.words[wordIndex];
            word.is_special = true;
            // Inherit current global style
            word.style_override = JSON.parse(JSON.stringify(subtitleTrack.global_style || {}));
        }
    });

    // Update timeline data to reflect special words
    if (timeline) {
        timeline.segments.text = subtitleTrack.segments;
        timeline.draw();
    }

    // Update preview to reflect special words
    preview?.setTrack(subtitleTrack);

    updateWordSelectionUI();
    autoSave();
    showToast('Marked as Special');
}

// Unmark selected words
function unmarkWords() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    selectedWords.forEach(({ segmentIndex, wordIndex }) => {
        const segment = subtitleTrack.segments[segmentIndex];
        if (segment && segment.words[wordIndex]) {
            const word = segment.words[wordIndex];
            word.is_special = false;
            word.group_id = null;
            word.style_override = null;
        }
    });

    // Clean up empty groups
    cleanupEmptyGroups();

    // Update timeline data to reflect changes
    if (timeline) {
        timeline.segments.text = subtitleTrack.segments;
        timeline.draw();
    }

    // Update preview to reflect changes
    preview?.setTrack(subtitleTrack);

    updateWordSelectionUI();
    updateSpecialsPanel();
    autoSave();
    showToast('Unmarked');
}

// Create a group from selected words
function createGroup() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    // Create new group with current global style
    const groupId = subtitleTrack.create_group();
    const group = subtitleTrack.special_groups[groupId];

    // Add all selected words to the group
    selectedWords.forEach(({ segmentIndex, wordIndex }) => {
        const segment = subtitleTrack.segments[segmentIndex];
        if (segment && segment.words[wordIndex]) {
            const word = segment.words[wordIndex];
            word.is_special = true;
            word.group_id = groupId;
            word.style_override = null;  // Use group style
        }
    });

    // Update timeline data to reflect special words
    if (timeline) {
        timeline.segments.text = subtitleTrack.segments;
        timeline.draw();
    }

    // Update preview to reflect special words
    preview?.setTrack(subtitleTrack);

    currentGroupId = groupId;
    updateWordSelectionUI();
    autoSave();
    showToast('Group created');
}

// Remove selected words from their group
function removeFromGroup() {
    if (!subtitleTrack || selectedWords.length === 0) return;

    selectedWords.forEach(({ segmentIndex, wordIndex }) => {
        const segment = subtitleTrack.segments[segmentIndex];
        if (segment && segment.words[wordIndex]) {
            const word = segment.words[wordIndex];
            word.group_id = null;
            word.is_special = false;
            word.style_override = null;
        }
    });

    // Clean up empty groups
    cleanupEmptyGroups();

    // Update timeline data to reflect changes
    if (timeline) {
        timeline.segments.text = subtitleTrack.segments;
        timeline.draw();
    }

    // Update preview to reflect changes
    preview?.setTrack(subtitleTrack);

    updateWordSelectionUI();
    updateSpecialsPanel();
    autoSave();
    showToast('Removed from group');
}

// Clean up empty groups
function cleanupEmptyGroups() {
    if (!subtitleTrack) return;

    const groupsToDelete = [];
    for (const [groupId, group] of Object.entries(subtitleTrack.special_groups)) {
        const members = subtitleTrack.get_group_members(groupId);
        if (members.length === 0) {
            groupsToDelete.push(groupId);
        }
    }

    groupsToDelete.forEach(groupId => {
        subtitleTrack.delete_group(groupId);
    });
}

// Initialize special style controls
function initSpecialStyleControls() {
    // §1 Font
    document.getElementById('special-font').addEventListener('change', (e) => {
        updateSpecialStyle('font_family', e.target.value);
    });
    document.getElementById('special-font-size').addEventListener('input', (e) => {
        document.getElementById('special-font-size-val').textContent = e.target.value;
        updateSpecialStyle('font_size', parseInt(e.target.value));
    });
    document.getElementById('special-font-weight').addEventListener('input', (e) => {
        document.getElementById('special-font-weight-val').textContent = e.target.value;
        updateSpecialStyle('font_weight', parseInt(e.target.value));
    });
    document.getElementById('special-font-style').addEventListener('change', (e) => {
        updateSpecialStyle('font_style', e.target.value);
    });
    document.getElementById('special-text-transform').addEventListener('change', (e) => {
        updateSpecialStyle('text_transform', e.target.value);
    });

    // §2 Fill
    document.getElementById('special-fill-type').addEventListener('change', (e) => {
        updateSpecialStyle('fill_type', e.target.value);
        toggleFillControls('special', e.target.value);
    });
    document.getElementById('special-text-color').addEventListener('input', (e) => {
        updateSpecialStyle('text_color', e.target.value);
    });
    document.getElementById('special-grad-color1').addEventListener('input', (e) => {
        updateSpecialStyle('gradient_color1', e.target.value);
    });
    document.getElementById('special-grad-color2').addEventListener('input', (e) => {
        updateSpecialStyle('gradient_color2', e.target.value);
    });
    document.getElementById('special-grad-angle').addEventListener('input', (e) => {
        document.getElementById('special-grad-angle-val').textContent = `${e.target.value}°`;
        updateSpecialStyle('gradient_angle', parseInt(e.target.value));
    });
    document.getElementById('special-grad-type').addEventListener('change', (e) => {
        updateSpecialStyle('gradient_type', e.target.value);
    });

    // §3 Stroke
    document.getElementById('special-stroke-enabled').addEventListener('change', (e) => {
        updateSpecialStyle('stroke_enabled', e.target.checked);
        toggleStrokeControls('special', e.target.checked);
    });
    document.getElementById('special-outline-color').addEventListener('input', (e) => {
        updateSpecialStyle('outline_color', e.target.value);
    });
    document.getElementById('special-outline-width').addEventListener('input', (e) => {
        document.getElementById('special-outline-w-val').textContent = e.target.value;
        updateSpecialStyle('outline_width', parseInt(e.target.value));
    });

    // §4 Shadow
    document.getElementById('special-shadow-enabled').addEventListener('change', (e) => {
        updateSpecialStyle('shadow_enabled', e.target.checked);
        toggleShadowControls('special', e.target.checked);
    });
    document.getElementById('special-shadow-color').addEventListener('input', (e) => {
        updateSpecialStyle('shadow_color', e.target.value);
    });
    document.getElementById('special-shadow-blur').addEventListener('input', (e) => {
        document.getElementById('special-shadow-blur-val').textContent = e.target.value;
        updateSpecialStyle('shadow_blur', parseInt(e.target.value));
    });
    document.getElementById('special-shadow-ox').addEventListener('input', (e) => {
        document.getElementById('special-shadow-ox-val').textContent = e.target.value;
        updateSpecialStyle('shadow_offset_x', parseInt(e.target.value));
    });
    document.getElementById('special-shadow-oy').addEventListener('input', (e) => {
        document.getElementById('special-shadow-oy-val').textContent = e.target.value;
        updateSpecialStyle('shadow_offset_y', parseInt(e.target.value));
    });

    // §5 Spacing
    document.getElementById('special-letter-spacing').addEventListener('input', (e) => {
        document.getElementById('special-letter-spacing-val').textContent = e.target.value;
        updateSpecialStyle('letter_spacing', parseFloat(e.target.value));
    });
    document.getElementById('special-word-spacing').addEventListener('input', (e) => {
        document.getElementById('special-word-spacing-val').textContent = e.target.value;
        updateSpecialStyle('word_spacing', parseFloat(e.target.value));
    });
    document.getElementById('special-line-height').addEventListener('input', (e) => {
        document.getElementById('special-line-height-val').textContent = e.target.value;
        updateSpecialStyle('line_height', parseFloat(e.target.value));
    });

    // §6 Opacity
    document.getElementById('special-opacity').addEventListener('input', (e) => {
        document.getElementById('special-opacity-val').textContent = e.target.value;
        updateSpecialStyle('text_opacity', parseInt(e.target.value) / 100);
    });
}

// Update special style for selected words
function updateSpecialStyle(property, value) {
    if (!subtitleTrack || selectedWords.length === 0) return;

    // Check if all selected words are in the same group
    const firstWord = getSelectedWord();
    if (!firstWord) return;

    const allInSameGroup = selectedWords.every(({ segmentIndex, wordIndex }) => {
        const seg = subtitleTrack.segments[segmentIndex];
        const w = seg?.words[wordIndex];
        return w && w.group_id === firstWord.group_id;
    });

    if (allInSameGroup && firstWord.group_id) {
        // Update group style
        const group = subtitleTrack.special_groups[firstWord.group_id];
        if (group) {
            group.style[property] = value;
        }
    } else {
        // Update individual word styles
        selectedWords.forEach(({ segmentIndex, wordIndex }) => {
            const segment = subtitleTrack.segments[segmentIndex];
            if (segment && segment.words[wordIndex]) {
                const word = segment.words[wordIndex];
                if (!word.style_override) {
                    // Create a deep copy of global_style
                    word.style_override = JSON.parse(JSON.stringify(subtitleTrack.global_style || {}));
                }
                word.style_override[property] = value;
            }
        });
    }

    // Update preview
    preview?.setTrack(subtitleTrack);

    // Update timeline to reflect changes
    if (timeline) {
        timeline.draw();
    }

    autoSave();
}

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
    document.getElementById('global-wpl').addEventListener('input', (e) => {
        document.getElementById('global-wpl-val').textContent = e.target.value;
        if (subtitleTrack) {
            subtitleTrack.words_per_line = parseInt(e.target.value);
            const allWords = [];
            for (const seg of subtitleTrack.segments) {
                allWords.push(...seg.words);
            }
            subtitleTrack.segments = [];
            for (let i = 0; i < allWords.length; i += subtitleTrack.words_per_line) {
                const chunk = allWords.slice(i, i + subtitleTrack.words_per_line);
                subtitleTrack.segments.push({
                    words: chunk,
                    style: JSON.parse(JSON.stringify(subtitleTrack.global_style || {}))
                });
            }
            populateSegments(subtitleTrack.segments);
            populateFullText(subtitleTrack.segments);
            preview?.setTrack(subtitleTrack);
            timeline?.setData(subtitleTrack, project.video_duration, project.id);
            autoSave();
        }
    });

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
 * Generates a deterministic HSL color based on a group ID.
 * @param {string} groupId The group UUID
 * @param {number} alpha Opacity (0-1)
 * @returns {string} HSLA color string
 */
function getGroupColor(groupId, alpha = 0.4) {
    if (!groupId) return `rgba(255, 215, 0, ${alpha})`; // Default yellow for special words without group
    
    let hash = 0;
    for (let i = 0; i < groupId.length; i++) {
        hash = groupId.charCodeAt(i) + ((hash << 5) - hash);
    }
    
    const hue = Math.abs(hash % 360);
    return `hsla(${hue}, 80%, 50%, ${alpha})`;
}

// Override populateSegments to support word selection
const originalPopulateSegments = populateSegments;
populateSegments = function(segments) {
    const panel = document.getElementById('segments-panel');

    if (!segments || segments.length === 0) {
        panel.innerHTML = '<p class="text-sm text-slate-400">No transcript segments.</p>';
        return;
    }

    panel.innerHTML = segments.map((seg, segIdx) => {
        const startTime = seg.words?.[0]?.start_time || 0;
        const endTime = seg.words?.[seg.words.length - 1]?.end_time || 0;

        // Build word HTML with special highlighting
        const wordsHtml = seg.words?.map((word, wordIdx) => {
            const isSpecial = word.is_special === true;
            let styleAttr = '';
            let specialClass = '';
            
            if (isSpecial) {
                const bgColor = getGroupColor(word.group_id, 0.2);
                const borderColor = getGroupColor(word.group_id, 0.5);
                styleAttr = `style="background-color: ${bgColor}; border: 1px solid ${borderColor};"`;
                specialClass = 'is-special'; // For targeted UI updates if needed
            }
            
            return `<span class="word-item px-1 rounded cursor-pointer hover:bg-white/10 transition-colors ${specialClass}" ${styleAttr} data-segment-idx="${segIdx}" data-word-idx="${wordIdx}">${escapeHtml(word.word)}</span>`;
        }).join(' ') || '';

        return `
            <div class="segment-item p-2 rounded-lg border border-transparent hover:border-white/10 hover:bg-white/5 cursor-pointer transition-all" data-idx="${segIdx}">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-[10px] text-primary font-mono">${formatDuration(startTime)}</span>
                    <span class="text-[10px] text-slate-500">→</span>
                    <span class="text-[10px] text-primary font-mono">${formatDuration(endTime)}</span>
                </div>
                <p class="text-sm text-slate-200 leading-relaxed">${wordsHtml}</p>
            </div>
        `;
    }).join('');

    // Click handler for segments
    panel.querySelectorAll('.segment-item').forEach(item => {
        item.addEventListener('click', (e) => {
            // Don't trigger if clicking on a word
            if (e.target.closest('.word-item')) return;

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

    // Re-apply word selection
    updateWordSelectionUI();

    // Re-attach word selection event listeners after innerHTML replacement
    attachWordSelectionListeners();
};

// Attach word selection event listeners to the segments panel
function attachWordSelectionListeners() {
    const panel = document.getElementById('segments-panel');
    if (!panel) return;

    console.log('[attachWordSelectionListeners] Attaching listeners to panel');

    // Remove old listeners by cloning
    const newPanel = panel.cloneNode(true);
    panel.parentNode.replaceChild(newPanel, panel);

    // Add click handler for word selection
    newPanel.addEventListener('click', (e) => {
        const wordEl = e.target.closest('.word-item');
        if (wordEl) {
            e.stopPropagation();
            console.log('[Word Click] wordEl:', wordEl);
            handleWordClick(wordEl, e.ctrlKey || e.metaKey);
        }
    });

    // Add context menu handler
    newPanel.addEventListener('contextmenu', (e) => {
        const wordEl = e.target.closest('.word-item');
        if (wordEl) {
            e.preventDefault();
            showContextMenu(e.clientX, e.clientY, wordEl);
        }
    });
}

// Initialize the styling system
document.addEventListener('DOMContentLoaded', () => {
    initStylingSystem();
});
