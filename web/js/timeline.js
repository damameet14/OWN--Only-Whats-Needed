/**
 * OWN — Canvas-based timeline widget.
 */

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

class SubtitleTimeline {
    constructor(canvasEl, wrapperEl) {
        this.canvas = canvasEl;
        this.wrapper = wrapperEl;
        this.ctx = canvasEl.getContext('2d');
        this.segments = { video: [], audio: [], text: [] };
        this.duration = 0;
        this.currentTime = 0;
        this.zoom = 1;
        this.scrollOffset = 0;
        this.selectedIndex = { track: null, index: -1 };
        this.selectionRange = null; // { start: float, end: float }
        this.onSeek = null;
        this.onSelect = null;

        this.setupEvents();
    }

    setData(segmentsData, duration, projectId = null) {
        // segmentsData should have { video: [], audio: [], text: [] }
        if (Array.isArray(segmentsData)) {
            // Fallback for old calls
            this.segments = { video: [], audio: [], text: segmentsData };
        } else {
            this.segments = {
                video: segmentsData.video_segments || [],
                audio: segmentsData.audio_segments || [],
                text: segmentsData.segments || []
            };
        }
        
        this.duration = duration || 0;
        this.projectId = projectId;
        
        // Load assets asynchronously if projectId is provided
        if (this.projectId) {
            this.loadAssets();
        }
        
        this.draw();
    }

    loadAssets() {
        this.spriteImg = new Image();
        this.spriteImg.src = `/api/projects/${this.projectId}/timeline_sprite`;
        this.spriteImg.onload = () => this.draw();

        this.waveformImg = new Image();
        this.waveformImg.src = `/api/projects/${this.projectId}/waveform`;
        this.waveformImg.onload = () => this.draw();
    }

    setCurrentTime(time) {
        this.currentTime = time;
        this.draw();
    }

    setupEvents() {
        let isDraggingPlayhead = false;
        let isDraggingSelection = false;
        let selectionStartPointer = 0;

        const handleInteraction = (e, isDown, forceSeek = false) => {
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const pxPerSec = this.getPixelsPerSecond();
            const trackH = (this.canvas.height - 32) / 3;
            const vidY = 24;
            const audY = 24 + trackH;
            const subY = 24 + trackH * 2;
            const headerW = 85;

            // Handle segment selection only on mouse down (if not shift key)
            if (isDown && !e.shiftKey) {
                let clickedTrack = null;
                let clickedSegList = null;
                
                if (y >= vidY && y < audY) { clickedTrack = 'video'; clickedSegList = this.segments.video; }
                else if (y >= audY && y < subY) { clickedTrack = 'audio'; clickedSegList = this.segments.audio; }
                else if (y >= subY && y <= subY + trackH) { clickedTrack = 'text'; clickedSegList = this.segments.text; }

                if (clickedSegList && clickedSegList.length > 0) {
                    for (let i = 0; i < clickedSegList.length; i++) {
                        const seg = clickedSegList[i];
                        const startTime = (clickedTrack === 'text') ? (seg.words?.[0]?.start_time || 0) : seg.start;
                        const endTime = (clickedTrack === 'text') ? (seg.words?.[seg.words.length - 1]?.end_time || 0) : seg.end;
                        const sx = headerW + startTime * pxPerSec - this.scrollOffset;
                        const sw = (endTime - startTime) * pxPerSec;

                        if (x >= sx && x <= sx + sw) {
                            this.selectedIndex = { track: clickedTrack, index: i };
                            if (this.onSelect) this.onSelect({ track: clickedTrack, index: i });
                            if (this.onSeek) this.onSeek(startTime);
                            this.currentTime = startTime; // Immediately update timeline visual playhead too
                            this.draw();
                            return true; // Clicked segment, don't drag playhead
                        }
                    }
                }
                
                // Clear selection if clicked blank space in tracks
                if (y >= 24) {
                    this.selectedIndex = { track: null, index: -1 };
                    if (this.onSelect) this.onSelect({ track: null, index: -1 });
                }
            }

            // Scrubbing playhead (if not shift-dragging)
            if (!isDraggingSelection) {
                const seekTime = Math.max(0, Math.min((x - headerW + this.scrollOffset) / pxPerSec, this.duration));
                this.currentTime = seekTime;
                this.draw(); // Instantly update playhead visually
                const now = Date.now();
                if (this.onSeek && (forceSeek || !this.lastSeek || now - this.lastSeek > 50)) {
                    this.lastSeek = now;
                    this.onSeek(seekTime);
                }
                this.selectionRange = null; // Clear selection area when seeking normally
            }
            return false;
        };

        this.canvas.addEventListener('mousedown', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const pxPerSec = this.getPixelsPerSecond();
            const headerW = 85;
            const playheadX = headerW + this.currentTime * pxPerSec - this.scrollOffset;

            // Prioritize scrubbing the playhead if clicked very close to it
            if (Math.abs(x - playheadX) < 15) {
                isDraggingPlayhead = true;
                handleInteraction(e, false, true); // pass false for isDown to prevent segment selection
                return;
            }
            
            if (y >= 24) { // Below ruler
                if (e.shiftKey) {
                    // Start selection range
                    const time = Math.max(0, Math.min((x - headerW + this.scrollOffset) / pxPerSec, this.duration));
                    isDraggingSelection = true;
                    selectionStartPointer = time;
                    this.selectionRange = { start: time, end: time };
                    this.draw();
                } else {
                    const clickedSegment = handleInteraction(e, true, true);
                    isDraggingPlayhead = !clickedSegment; // Only drag playhead if we clicked empty space
                }
            } else { // Clicked on the ruler
                isDraggingPlayhead = true;
                handleInteraction(e, false, true);
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (isDraggingSelection) {
                const rect = this.canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const pxPerSec = this.getPixelsPerSecond();
                const headerW = 85;
                const time = Math.max(0, Math.min((x - headerW + this.scrollOffset) / pxPerSec, this.duration));
                this.selectionRange = { 
                    start: Math.min(selectionStartPointer, time), 
                    end: Math.max(selectionStartPointer, time) 
                };
                this.draw();
            } else if (isDraggingPlayhead) {
                handleInteraction(e, false);
            }
        });

        window.addEventListener('mouseup', (e) => {
            if (isDraggingSelection) {
                isDraggingSelection = false;
            }
            if (isDraggingPlayhead) {
                isDraggingPlayhead = false;
                handleInteraction(e, false, true);
            }
        });

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.ctrlKey || e.metaKey) {
                const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
                this.zoom = Math.max(0.5, Math.min(this.zoom * zoomFactor, 20));
            } else {
                const pxPerSec = this.getPixelsPerSecond();
                const headerW = 85;
                const maxScroll = Math.max(0, this.duration * pxPerSec - (this.canvas.width - headerW) + 100);
                this.scrollOffset = Math.max(0, Math.min(this.scrollOffset + (e.deltaX || e.deltaY), maxScroll));
            }
            this.draw();
        }, { passive: false });

        // Zoom buttons and slider
        document.getElementById('btn-zoom-in')?.addEventListener('click', () => {
            this.zoom = Math.min(this.zoom * 1.5, 20);
            this.updateZoomSlider();
            this.draw();
        });
        document.getElementById('btn-zoom-out')?.addEventListener('click', () => {
            this.zoom = Math.max(this.zoom / 1.5, 0.5);
            this.updateZoomSlider();
            this.draw();
        });
        const zoomSlider = document.getElementById('zoom-slider');
        if (zoomSlider) {
            zoomSlider.addEventListener('input', (e) => {
                this.zoom = parseFloat(e.target.value);
                this.draw();
            });
        }
        
        // Setup resizing drag
        const resizer = document.getElementById('timeline-resizer');
        const container = document.getElementById('timeline-container');
        if (resizer && container) {
            let isResizing = false;
            let startY, startHeight;

            resizer.addEventListener('mousedown', (e) => {
                isResizing = true;
                startY = e.clientY;
                startHeight = container.getBoundingClientRect().height;
                e.preventDefault();
            });

            window.addEventListener('mousemove', (e) => {
                if (!isResizing) return;
                const newHeight = startHeight - (e.clientY - startY);
                container.style.height = `${Math.max(100, Math.min(600, newHeight))}px`;
                this.draw();
            });

            window.addEventListener('mouseup', () => {
                isResizing = false;
            });
        }
    }

    updateZoomSlider() {
        const zoomSlider = document.getElementById('zoom-slider');
        if (zoomSlider) {
            zoomSlider.value = this.zoom;
        }
    }

    getPixelsPerSecond() {
        if (this.duration <= 0) return 50;
        const headerW = 85;
        // The displayable width ignores the sticky panel:
        return ((this.canvas.width - headerW) / this.duration) * this.zoom;
    }

    draw() {
        const canvas = this.canvas;
        const ctx = this.ctx;
        const rect = this.wrapper.getBoundingClientRect();

        canvas.width = rect.width;
        canvas.height = rect.height;

        const w = canvas.width;
        const h = canvas.height;
        const pxPerSec = this.getPixelsPerSecond();

        // Background
        ctx.fillStyle = '#2d2914';
        ctx.fillRect(0, 0, w, h);

        // Time ruler
        ctx.fillStyle = '#a8a48e';
        ctx.font = '10px Inter, sans-serif';
        ctx.textBaseline = 'top';

        const headerW = 85;
        const startX = headerW - this.scrollOffset;
        
        ctx.save();
        ctx.beginPath();
        // Clip track area (prevent drawing under sticky headers)
        ctx.rect(headerW, 0, w - headerW, h);
        ctx.clip();

        const step = this.getTimeStep();
        for (let t = 0; t <= this.duration; t += step) {
            const x = startX + t * pxPerSec;
            if (x < headerW - 50 || x > w + 50) continue;

            ctx.fillStyle = '#a8a48e';
            ctx.fillText(this.formatTime(t), x + 2, 2);

            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.beginPath();
            ctx.moveTo(x, 16);
            ctx.lineTo(x, h);
            ctx.stroke();
        }

        // Draw Track Backgrounds and Data
        const trackY = 24;
        const totalTrackH = h - 32;
        const trackH = totalTrackH / 3;
        const contentWidth = this.duration * pxPerSec;

        // Helper to draw segment blocks for Video and Audio
        const drawMediaSegments = (segments, y, color, isSelectedTrack) => {
            if (!segments) return;
            for (let i = 0; i < segments.length; i++) {
                const seg = segments[i];
                const x = startX + seg.start * pxPerSec;
                const sw = Math.max((seg.end - seg.start) * pxPerSec, 2);
                
                if (x > w || x + sw < headerW) continue; // Culling

                // We'll mask the sprite/waveform within this segment block
                ctx.save();
                ctx.beginPath();
                ctx.rect(x, y + 2, sw, trackH - 4);
                ctx.clip();

                if (isSelectedTrack && this.spriteImg && this.spriteImg.complete && this.spriteImg.naturalWidth > 0) {
                    // For video sprite, we stretch the whole sprite over duration, but clip to segment
                    ctx.drawImage(this.spriteImg, startX, y + 2, contentWidth, trackH - 4);
                } else if (!isSelectedTrack && this.waveformImg && this.waveformImg.complete && this.waveformImg.naturalWidth > 0) {
                    ctx.drawImage(this.waveformImg, startX, y + 2, contentWidth, trackH - 4);
                } else {
                    ctx.fillStyle = color;
                    ctx.fillRect(x, y + 2, sw, trackH - 4);
                }
                
                // Draw borders if selected
                const isSel = (this.selectedIndex.track === (isSelectedTrack ? 'video' : 'audio') && this.selectedIndex.index === i);
                if (isSel) {
                    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
                    ctx.fillRect(x, y + 2, sw, trackH - 4);
                    ctx.strokeStyle = '#fff';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(x, y + 2, sw, trackH - 4);
                } else {
                    ctx.strokeStyle = 'rgba(0,0,0,0.5)';
                    ctx.lineWidth = 1;
                    ctx.strokeRect(x, y + 2, sw, trackH - 4);
                }
                ctx.restore();
            }
        };

        // --- Video Track ---
        ctx.fillStyle = '#1c1a0e';
        ctx.fillRect(headerW, trackY, w - headerW, trackH);
        drawMediaSegments(this.segments.video, trackY, '#3a5a78', true);

        // --- Audio Track ---
        ctx.fillStyle = '#23200f';
        ctx.fillRect(headerW, trackY + trackH, w - headerW, trackH);
        drawMediaSegments(this.segments.audio, trackY + trackH, '#5a783a', false);

        // --- Subtitle Track Background ---
        const subTrackY = trackY + trackH * 2;
        ctx.fillStyle = '#352f1a';
        ctx.fillRect(headerW, subTrackY, w - headerW, trackH);

        // Segments (Subtitles)
        if (this.segments.text) {
            for (let i = 0; i < this.segments.text.length; i++) {
                const seg = this.segments.text[i];
                const startTime = seg.words?.[0]?.start_time || 0;
                const endTime = seg.words?.[seg.words.length - 1]?.end_time || 0;
                const x = startX + startTime * pxPerSec;
                const sw = Math.max((endTime - startTime) * pxPerSec, 2);

                if (x > w || x + sw < headerW) continue; // Culling

                const isSelected = (this.selectedIndex.track === 'text' && this.selectedIndex.index === i);

                ctx.fillStyle = isSelected ? 'rgba(255, 231, 77, 0.5)' : 'rgba(255, 231, 77, 0.25)';
                ctx.fillRect(x, subTrackY + 2, sw, trackH - 4);

                ctx.strokeStyle = isSelected ? '#ffe74d' : 'rgba(255, 231, 77, 0.5)';
                ctx.lineWidth = isSelected ? 2 : 1;
                ctx.strokeRect(x, subTrackY + 2, sw, trackH - 4);



                // Segment text (if wide enough)
                if (sw > 40) {
                    const text = seg.words?.map(w => w.word).join(' ') || '';
                    ctx.fillStyle = '#fff';
                    ctx.font = '10px Inter, sans-serif';
                    ctx.save();
                    ctx.beginPath();
                    ctx.rect(x, subTrackY, sw, trackH);
                    ctx.clip();
                    ctx.fillText(text, x + 4, subTrackY + trackH / 2 - 4);
                    ctx.restore();
                }
            }
        }

        // Draw Time Selection Range if active
        if (this.selectionRange) {
            const rangeStart = startX + this.selectionRange.start * pxPerSec;
            const rangeEnd = startX + this.selectionRange.end * pxPerSec;
            if (rangeEnd > rangeStart) {
                ctx.fillStyle = 'rgba(77, 184, 255, 0.3)';
                ctx.fillRect(rangeStart, trackY, rangeEnd - rangeStart, trackH * 3);
                ctx.strokeStyle = 'rgba(77, 184, 255, 0.8)';
                ctx.lineWidth = 1;
                ctx.strokeRect(rangeStart, trackY, rangeEnd - rangeStart, trackH * 3);
            }
        }

        ctx.restore(); // Undo the clip to draw the headers properly

        // Right panel overlay (track sticky headers)
        ctx.fillStyle = '#1c1a0e'; // Solid background for headers
        ctx.fillRect(0, 0, headerW, h); // Cover from top to bottom
        // Border line separating header from tracks
        ctx.strokeStyle = 'rgba(255,255,255,0.05)';
        ctx.beginPath();
        ctx.moveTo(headerW, 0);
        ctx.lineTo(headerW, h);
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 10px Inter, sans-serif';
        ctx.textBaseline = 'middle';
        // Video
        ctx.fillText('🎬 VIDEO', 10, trackY + trackH / 2);
        // Audio
        ctx.fillText('🎧 AUDIO', 10, trackY + trackH + trackH / 2);
        // Text
        ctx.fillText('📝 TEXT', 10, subTrackY + trackH / 2);

        // Playhead
        let playheadX = startX + this.currentTime * pxPerSec;
        // Clamp to left border
        playheadX = Math.max(headerW, playheadX);

        ctx.strokeStyle = '#ff4444';
        ctx.fillStyle = '#ff4444';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(playheadX, 0);
        ctx.lineTo(playheadX, h);
        ctx.stroke();
        
        // Playhead triangle top
        ctx.beginPath();
        ctx.moveTo(playheadX - 6, 0);
        ctx.lineTo(playheadX + 6, 0);
        ctx.lineTo(playheadX, 10);
        ctx.fill();
        ctx.lineWidth = 1;
    }

    getTimeStep() {
        const pxPerSec = this.getPixelsPerSecond();
        if (pxPerSec > 200) return 1;
        if (pxPerSec > 50) return 5;
        if (pxPerSec > 20) return 10;
        if (pxPerSec > 5) return 30;
        return 60;
    }

    formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${String(s).padStart(2, '0')}`;
    }
}
