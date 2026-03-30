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
    initStyleControls();
    initTabSwitching();
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

async function loadProject(id) {
    try {
        project = await getProject(id);
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
        }

        // Initialize preview
        const canvas = document.getElementById('subtitle-canvas');
        preview = new SubtitlePreview(video, canvas);
        if (subtitleTrack) {
            preview.setTrack(subtitleTrack);
        }
        preview.start();

        // Initialize timeline
        const timelineCanvas = document.getElementById('timeline-canvas');
        const timelineWrapper = document.getElementById('timeline-wrapper');
        timeline = new SubtitleTimeline(timelineCanvas, timelineWrapper);

        if (subtitleTrack) {
            // BACKWARDS COMPATIBILITY: Initialize multi-track segments if missing
            if (!subtitleTrack.video_segments || subtitleTrack.video_segments.length === 0) {
                subtitleTrack.video_segments = [{start: 0, end: project.video_duration, source_start: 0, source_end: project.video_duration}];
            }
            if (!subtitleTrack.audio_segments || subtitleTrack.audio_segments.length === 0) {
                subtitleTrack.audio_segments = [{start: 0, end: project.video_duration, source_start: 0, source_end: project.video_duration}];
            }

            timeline.setData(subtitleTrack, project.video_duration, project.id);
            populateSegments(subtitleTrack.segments);
            populateFullText(subtitleTrack.segments);
            applyTrackToControls(subtitleTrack);
        }

        // Subtitle Canvas Dragging
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
                        const newSeg = { ...seg, words: seg.words.map(w => ({...w, start_time: w.start_time - cutDuration, end_time: w.end_time - cutDuration})) };
                        newTextList.push(newSeg);
                    } else {
                        // Word by word trimming
                        const newWords = [];
                        for (let w of seg.words) {
                            if (w.end_time <= start) {
                                newWords.push(w);
                            } else if (w.start_time >= end) {
                                newWords.push({...w, start_time: w.start_time - cutDuration, end_time: w.end_time - cutDuration});
                            }
                            // Else drop words inside cut area
                        }
                        if (newWords.length > 0) {
                            newTextList.push({...seg, words: newWords});
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


// ── Style Controls ───────────────────────────────────────────────────────────

function initStyleControls() {
    // Font size
    const fontSizeSlider = document.getElementById('style-font-size');
    const fontSizeVal = document.getElementById('font-size-val');
    fontSizeSlider.addEventListener('input', () => {
        fontSizeVal.textContent = fontSizeSlider.value;
        updateStyle('font_size', parseInt(fontSizeSlider.value));
    });

    // Font family
    document.getElementById('style-font').addEventListener('change', (e) => {
        updateStyle('font_family', e.target.value);
    });

    // Colors
    document.getElementById('style-text-color').addEventListener('input', (e) => {
        updateStyle('text_color', e.target.value);
    });
    document.getElementById('style-outline-color').addEventListener('input', (e) => {
        updateStyle('outline_color', e.target.value);
    });

    // Outline width
    const outlineSlider = document.getElementById('style-outline-width');
    const outlineVal = document.getElementById('outline-w-val');
    outlineSlider.addEventListener('input', () => {
        outlineVal.textContent = outlineSlider.value;
        updateStyle('outline_width', parseInt(outlineSlider.value));
    });

    // Bold / Italic
    document.getElementById('style-bold').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const isBold = btn.classList.toggle('bg-primary/30');
        updateStyle('bold', isBold);
    });
    document.getElementById('style-italic').addEventListener('click', (e) => {
        const btn = e.currentTarget;
        const isItalic = btn.classList.toggle('bg-primary/30');
        updateStyle('italic', isItalic);
    });

    // Position Y
    const posYSlider = document.getElementById('style-pos-y');
    const posYVal = document.getElementById('pos-y-val');
    posYSlider.addEventListener('input', () => {
        posYVal.textContent = `${posYSlider.value}%`;
        if (subtitleTrack) {
            subtitleTrack.position_y = parseInt(posYSlider.value) / 100;
            preview?.setTrack(subtitleTrack);
            autoSave();
        }
    });

    // Words per line
    const wplSlider = document.getElementById('style-wpl');
    const wplVal = document.getElementById('wpl-val');
    wplSlider.addEventListener('input', () => {
        wplVal.textContent = wplSlider.value;
        if (subtitleTrack) {
            subtitleTrack.words_per_line = parseInt(wplSlider.value);
            // Note: changing WPL would ideally re-segment, but we keep it simple
            autoSave();
        }
    });

    // Subtitle Rotation
    const subRotSlider = document.getElementById('style-sub-rotation');
    const subRotVal = document.getElementById('sub-rot-val');
    if (subRotSlider) {
        subRotSlider.addEventListener('input', () => {
            subRotVal.textContent = `${subRotSlider.value}°`;
            updateStyle('rotation', parseInt(subRotSlider.value));
        });
    }

    // Video Rotation
    const vidRotSlider = document.getElementById('style-vid-rotation');
    const vidRotVal = document.getElementById('vid-rot-val');
    if (vidRotSlider) {
        vidRotSlider.addEventListener('input', () => {
            vidRotVal.textContent = `${vidRotSlider.value}°`;
            if (subtitleTrack) {
                subtitleTrack.video_rotation = parseInt(vidRotSlider.value);
                const video = document.getElementById('video-player');
                if (video) {
                    video.style.transform = `rotate(${subtitleTrack.video_rotation}deg)`;
                }
                autoSave();
            }
        });
    }

    // Shadow toggle
    document.getElementById('style-shadow').addEventListener('change', (e) => {
        if (e.target.checked) {
            updateStyle('shadow_color', '#80000000');
            updateStyle('shadow_offset_x', 2);
            updateStyle('shadow_offset_y', 2);
        } else {
            updateStyle('shadow_color', '');
            updateStyle('shadow_offset_x', 0);
            updateStyle('shadow_offset_y', 0);
        }
    });

    // Animation type
    document.getElementById('style-animation').addEventListener('change', (e) => {
        if (subtitleTrack) {
            subtitleTrack.animation_type = e.target.value;
            preview?.setTrack(subtitleTrack);
            autoSave();
        }
    });

    // Animation duration
    const animDurSlider = document.getElementById('style-anim-duration');
    const animDurVal = document.getElementById('anim-dur-val');
    animDurSlider.addEventListener('input', () => {
        animDurVal.textContent = `${animDurSlider.value}s`;
        if (subtitleTrack) {
            subtitleTrack.animation_duration = parseFloat(animDurSlider.value);
            preview?.setTrack(subtitleTrack);
            autoSave();
        }
    });
}

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

    setVal('style-font', style.font_family || 'Noto Sans Devanagari');
    setVal('style-font-size', style.font_size || 48);
    document.getElementById('font-size-val').textContent = style.font_size || 48;
    setVal('style-text-color', style.text_color || '#FFFFFF');
    setVal('style-outline-color', style.outline_color || '#000000');
    setVal('style-outline-width', style.outline_width ?? 2);
    document.getElementById('outline-w-val').textContent = style.outline_width ?? 2;
    setVal('style-pos-y', Math.round((track.position_y || 0.9) * 100));
    document.getElementById('pos-y-val').textContent = `${Math.round((track.position_y || 0.9) * 100)}%`;

    setVal('style-sub-rotation', style.rotation || 0);
    const subVal = document.getElementById('sub-rot-val');
    if (subVal) subVal.textContent = `${style.rotation || 0}°`;

    setVal('style-vid-rotation', track.video_rotation || 0);
    const vidVal = document.getElementById('vid-rot-val');
    if (vidVal) vidVal.textContent = `${track.video_rotation || 0}°`;

    const video = document.getElementById('video-player');
    if (video) {
        video.style.transform = `rotate(${track.video_rotation || 0}deg)`;
    }

    setVal('style-wpl', track.words_per_line || 5);
    document.getElementById('wpl-val').textContent = track.words_per_line || 5;
    setVal('style-animation', track.animation_type || 'none');
    setVal('style-anim-duration', track.animation_duration || 0.3);
    document.getElementById('anim-dur-val').textContent = `${track.animation_duration || 0.3}s`;

    if (style.bold) document.getElementById('style-bold').classList.add('bg-primary/30');
    if (style.italic) document.getElementById('style-italic').classList.add('bg-primary/30');
    document.getElementById('style-shadow').checked = !!(style.shadow_color);
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
    const panel = document.getElementById('templates-panel');
    try {
        const presets = await getPresets();
        if (!presets.length) {
            panel.innerHTML = '<p class="text-sm text-slate-400">No presets available.</p>';
            return;
        }

        panel.innerHTML = presets.map((preset, idx) => `
            <div class="preset-card p-3 rounded-lg border border-white/10 bg-white/5 cursor-pointer hover:border-primary/30 transition-all" data-idx="${idx}">
                <div class="text-sm font-bold text-white mb-1">${escapeHtml(preset.name)}</div>
                <div class="text-xs text-slate-400">${escapeHtml(preset.description || '')}</div>
                <div class="mt-2 text-lg font-bold" style="color: ${preset.style?.text_color || '#fff'}; text-shadow: 1px 1px 2px ${preset.style?.outline_color || '#000'};">
                    Sample सैम्पल
                </div>
            </div>
        `).join('');

        panel.querySelectorAll('.preset-card').forEach(card => {
            card.addEventListener('click', () => {
                const idx = parseInt(card.dataset.idx);
                const preset = presets[idx];
                if (preset.style && subtitleTrack) {
                    // Apply preset style
                    subtitleTrack.global_style = { ...subtitleTrack.global_style, ...preset.style };
                    if (subtitleTrack.segments) {
                        for (const seg of subtitleTrack.segments) {
                            seg.style = { ...seg.style, ...preset.style };
                        }
                    }
                    preview?.setTrack(subtitleTrack);
                    applyTrackToControls(subtitleTrack);
                    autoSave();
                    showToast(`Applied "${preset.name}" style`);
                }
            });
        });
    } catch (err) {
        panel.innerHTML = `<p class="text-sm text-red-400">Error loading presets.</p>`;
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

    btnTranscribe.addEventListener('click', () => showModal(modal));
    btnCancel.addEventListener('click', () => hideModal(modal));

    btnStart.addEventListener('click', async () => {
        const engine = document.getElementById('transcribe-engine')?.value || 'vosk';
        const model = document.getElementById('transcribe-model')?.value || null;

        const progressWrap = document.getElementById('transcribe-progress-wrap');
        const statusEl = document.getElementById('transcribe-status');
        const barEl = document.getElementById('transcribe-progress-bar');
        const buttons = document.getElementById('transcribe-buttons');

        progressWrap.classList.remove('hidden');
        buttons.classList.add('hidden');

        try {
            const { task_id } = await startTranscription(project.id, { engine, model });

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
                    // Reload project to get subtitle data
                    loadProject(project.id);
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
