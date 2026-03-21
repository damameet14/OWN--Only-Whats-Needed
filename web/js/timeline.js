/**
 * OWN — Canvas-based timeline widget.
 */

class SubtitleTimeline {
    constructor(canvasEl, wrapperEl) {
        this.canvas = canvasEl;
        this.wrapper = wrapperEl;
        this.ctx = canvasEl.getContext('2d');
        this.segments = [];
        this.duration = 0;
        this.currentTime = 0;
        this.zoom = 1;
        this.scrollOffset = 0;
        this.selectedIndex = -1;
        this.onSeek = null;
        this.onSelect = null;

        this.setupEvents();
    }

    setData(segments, duration) {
        this.segments = segments || [];
        this.duration = duration || 0;
        this.draw();
    }

    setCurrentTime(time) {
        this.currentTime = time;
        this.draw();
    }

    setupEvents() {
        let isDragging = false;

        const handleInteraction = (e, isDown, forceSeek = false) => {
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const pxPerSec = this.getPixelsPerSecond();
            const trackH = (this.canvas.height - 32) / 3;
            const subTrackY = 24 + trackH * 2;

            // Handle segment selection only on mouse down
            if (isDown && y >= subTrackY && y <= subTrackY + trackH && this.segments.length > 0) {
                for (let i = 0; i < this.segments.length; i++) {
                    const seg = this.segments[i];
                    const startTime = seg.words?.[0]?.start_time || 0;
                    const endTime = seg.words?.[seg.words.length - 1]?.end_time || 0;
                    const sx = startTime * pxPerSec - this.scrollOffset;
                    const sw = (endTime - startTime) * pxPerSec;

                    if (x >= sx && x <= sx + sw) {
                        this.selectedIndex = i;
                        if (this.onSelect) this.onSelect(i);
                        if (this.onSeek) this.onSeek(startTime);
                        this.draw();
                        return; // Clicked segment, don't drag playhead
                    }
                }
            }

            // Scrubbing playhead
            const seekTime = Math.max(0, Math.min((x + this.scrollOffset) / pxPerSec, this.duration));
            const now = Date.now();
            if (this.onSeek && (forceSeek || !this.lastSeek || now - this.lastSeek > 100)) {
                this.lastSeek = now;
                this.onSeek(seekTime);
            }
        };

        this.canvas.addEventListener('mousedown', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const y = e.clientY - rect.top;
            if (y >= 24) { // Below ruler
                isDragging = true;
                handleInteraction(e, true, true);
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (isDragging) {
                handleInteraction(e, false);
            }
        });

        window.addEventListener('mouseup', (e) => {
            if (isDragging) {
                isDragging = false;
                handleInteraction(e, false, true);
            }
        });

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.ctrlKey || e.metaKey) {
                const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
                this.zoom = Math.max(0.5, Math.min(this.zoom * zoomFactor, 20));
            } else {
                const maxScroll = Math.max(0, this.duration * this.getPixelsPerSecond() - this.canvas.width + 100);
                this.scrollOffset = Math.max(0, Math.min(this.scrollOffset + (e.deltaX || e.deltaY), maxScroll));
            }
            this.draw();
        }, { passive: false });

        // Zoom buttons
        document.getElementById('btn-zoom-in')?.addEventListener('click', () => {
            this.zoom = Math.min(this.zoom * 1.5, 10);
            this.draw();
        });
        document.getElementById('btn-zoom-out')?.addEventListener('click', () => {
            this.zoom = Math.max(this.zoom / 1.5, 0.5);
            this.draw();
        });
    }

    getPixelsPerSecond() {
        if (this.duration <= 0) return 50;
        return (this.canvas.width / this.duration) * this.zoom;
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

        const step = this.getTimeStep();
        for (let t = 0; t <= this.duration; t += step) {
            const x = t * pxPerSec - this.scrollOffset;
            if (x < -50 || x > w + 50) continue;

            ctx.fillStyle = '#a8a48e';
            ctx.fillText(this.formatTime(t), x + 2, 2);

            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.beginPath();
            ctx.moveTo(x, 16);
            ctx.lineTo(x, h);
            ctx.stroke();
        }

        // Draw Tracks
        const trackY = 24;
        const totalTrackH = h - 32;
        const trackH = totalTrackH / 3;

        // Video Track
        ctx.fillStyle = '#23200f';
        ctx.fillRect(0, trackY, w, trackH);
        ctx.fillStyle = '#a8a48e';
        ctx.fillText('🎬 Video', 8, trackY + trackH / 2 - 5);
        
        const lastVideoX = this.duration * pxPerSec - this.scrollOffset;
        if (lastVideoX > 0) {
            ctx.fillStyle = '#3a5a78';
            ctx.fillRect(-this.scrollOffset, trackY + 2, this.duration * pxPerSec, trackH - 4);
        }

        // Audio Track
        ctx.fillStyle = '#2d2914';
        ctx.fillRect(0, trackY + trackH, w, trackH);
        ctx.fillStyle = '#a8a48e';
        ctx.fillText('🎵 Audio', 8, trackY + trackH + trackH / 2 - 5);
        
        if (lastVideoX > 0) {
            ctx.fillStyle = '#5a783a';
            ctx.fillRect(-this.scrollOffset, trackY + trackH + 2, this.duration * pxPerSec, trackH - 4);
        }

        // Subtitle Track
        const subTrackY = trackY + trackH * 2;
        ctx.fillStyle = '#352f1a';
        ctx.fillRect(0, subTrackY, w, trackH);
        ctx.fillStyle = '#a8a48e';
        // Only draw text if scrolled left
        if (this.scrollOffset < 50) {
            ctx.fillText('📝 Subtitles', 8, subTrackY + trackH / 2 - 5);
        }

        // Segments (Subtitles)
        for (let i = 0; i < this.segments.length; i++) {
            const seg = this.segments[i];
            const startTime = seg.words?.[0]?.start_time || 0;
            const endTime = seg.words?.[seg.words.length - 1]?.end_time || 0;
            const x = startTime * pxPerSec - this.scrollOffset;
            const sw = Math.max((endTime - startTime) * pxPerSec, 2);

            if (x > w || x + sw < 0) continue; // Culling

            const isSelected = i === this.selectedIndex;

            ctx.fillStyle = isSelected ? 'rgba(255, 231, 77, 0.5)' : 'rgba(255, 231, 77, 0.25)';
            ctx.fillRect(x, subTrackY + 2, sw, trackH - 4);

            ctx.strokeStyle = isSelected ? '#ffe74d' : 'rgba(255, 231, 77, 0.5)';
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

        // Playhead
        const playheadX = this.currentTime * pxPerSec - this.scrollOffset;
        ctx.strokeStyle = '#ff4444';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(playheadX, 0);
        ctx.lineTo(playheadX, h);
        ctx.stroke();
        ctx.lineWidth = 1;

        // Playhead triangle
        ctx.fillStyle = '#ff4444';
        ctx.beginPath();
        ctx.moveTo(playheadX - 5, 0);
        ctx.lineTo(playheadX + 5, 0);
        ctx.lineTo(playheadX, 8);
        ctx.closePath();
        ctx.fill();
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
