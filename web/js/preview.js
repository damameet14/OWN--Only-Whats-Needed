/**
 * OWN — Canvas-based subtitle preview overlay.
 * Renders subtitles on a <canvas> overlaying the <video> element.
 */

class SubtitlePreview {
    constructor(videoEl, canvasEl) {
        this.video = videoEl;
        this.canvas = canvasEl;
        this.ctx = canvasEl.getContext('2d');
        this.subtitleTrack = null;
        this.animationFrame = null;
        this.fonts = {};
    }

    setTrack(trackData) {
        this.subtitleTrack = trackData;
    }

    start() {
        this.render();
    }

    stop() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }
    }

    render() {
        this.resizeCanvas();
        this.draw();
        this.animationFrame = requestAnimationFrame(() => this.render());
    }

    resizeCanvas() {
        const rect = this.video.getBoundingClientRect();
        if (this.canvas.width !== rect.width || this.canvas.height !== rect.height) {
            this.canvas.width = rect.width;
            this.canvas.height = rect.height;
        }
    }

    draw() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;

        ctx.clearRect(0, 0, w, h);

        if (!this.subtitleTrack || !this.subtitleTrack.segments) return;

        const currentTime = this.video.currentTime;
        const track = this.subtitleTrack;

        // Find active segment
        let activeSeg = null;
        for (const seg of track.segments) {
            const startTime = seg.words.length > 0 ? seg.words[0].start_time : 0;
            const endTime = seg.words.length > 0 ? seg.words[seg.words.length - 1].end_time : 0;
            if (currentTime >= startTime && currentTime <= endTime) {
                activeSeg = seg;
                break;
            }
        }

        if (!activeSeg) return;

        const style = activeSeg.style || track.global_style || {};
        const posX = track.position_x || 0.5;
        const posY = track.position_y || 0.9;

        // Compute animation state
        const segStart = activeSeg.words[0]?.start_time || 0;
        const segEnd = activeSeg.words[activeSeg.words.length - 1]?.end_time || 0;
        const animType = track.animation_type || 'none';
        const animDur = track.animation_duration || 0.3;
        const animState = computeAnimState(animType, currentTime, segStart, segEnd, animDur, h);

        if (animState.opacity <= 0) return;

        // Build display text
        let displayText = activeSeg.words.map(w => w.word).join(' ');

        if (animType === 'typewriter' && animState.visibleChars >= 0) {
            displayText = displayText.substring(0, animState.visibleChars);
        }

        if (!displayText.trim()) return;

        // Scale font size based on canvas vs actual resolution
        const scaleFactor = w / (this.video.videoWidth || 1920);
        const fontSize = Math.round((style.font_size || 48) * scaleFactor);

        // Set font
        let fontStr = `${style.bold ? 'bold' : ''} ${style.italic ? 'italic' : ''} ${fontSize}px "${style.font_family || 'sans-serif'}"`.trim();
        ctx.font = fontStr;
        ctx.textBaseline = 'top';

        const metrics = ctx.measureText(displayText);
        const textW = metrics.width;
        const textH = fontSize * 1.2;

        let x = posX * w - textW / 2;
        let y = posY * h - textH;

        x += (animState.offsetX || 0) * scaleFactor;
        y += (animState.offsetY || 0) * scaleFactor;

        x = Math.max(0, Math.min(x, w - textW));
        y = Math.max(0, Math.min(y, h - textH));

        ctx.globalAlpha = animState.opacity;

        const rotationAngle = (style.rotation || 0) * Math.PI / 180;
        if (rotationAngle !== 0) {
            ctx.save();
            ctx.translate(x + textW / 2, y + textH / 2);
            ctx.rotate(rotationAngle);
            ctx.translate(-(x + textW / 2), -(y + textH / 2));
        }

        // Background box
        if (style.bg_color) {
            ctx.fillStyle = style.bg_color;
            const pad = (style.bg_padding || 8) * scaleFactor;
            ctx.fillRect(x - pad, y - pad, textW + 2 * pad, textH + 2 * pad);
        }

        // Shadow
        if (style.shadow_color && (style.shadow_offset_x || style.shadow_offset_y)) {
            ctx.fillStyle = style.shadow_color;
            ctx.fillText(displayText,
                x + (style.shadow_offset_x || 0) * scaleFactor,
                y + (style.shadow_offset_y || 0) * scaleFactor
            );
        }

        // Outline
        if (style.outline_color && style.outline_width > 0) {
            ctx.strokeStyle = style.outline_color;
            ctx.lineWidth = style.outline_width * scaleFactor * 2;
            ctx.lineJoin = 'round';
            ctx.strokeText(displayText, x, y);
        }

        // Karaoke highlight
        if (animType === 'karaoke' && animState.highlightIdx >= 0) {
            this.drawKaraoke(ctx, activeSeg, style, animState, x, y, fontSize, scaleFactor);
        } else {
            // Main text
            ctx.fillStyle = style.text_color || '#FFFFFF';
            ctx.fillText(displayText, x, y);
        }

        if (rotationAngle !== 0) {
            ctx.restore();
        }

        ctx.globalAlpha = 1;
    }

    drawKaraoke(ctx, seg, style, animState, baseX, baseY, fontSize, scale) {
        let curX = baseX;
        seg.words.forEach((word, idx) => {
            const text = word.word + ' ';
            if (idx === animState.highlightIdx) {
                ctx.fillStyle = '#FFD700';
                const hlFontSize = Math.round(fontSize * 1.15);
                const savedFont = ctx.font;
                ctx.font = ctx.font.replace(`${fontSize}px`, `${hlFontSize}px`);
                ctx.fillText(text, curX, baseY);
                curX += ctx.measureText(text).width;
                ctx.font = savedFont;
            } else {
                ctx.fillStyle = style.text_color || '#FFFFFF';
                ctx.fillText(text, curX, baseY);
                curX += ctx.measureText(text).width;
            }
        });
    }
}


// ── Animation State ──────────────────────────────────────────────────────────

function computeAnimState(type, current, segStart, segEnd, animDur, frameH) {
    const state = { opacity: 1, offsetX: 0, offsetY: 0, scale: 1, visibleChars: -1, highlightIdx: -1 };

    if (current < segStart || current > segEnd) {
        state.opacity = 0;
        return state;
    }

    const segDur = segEnd - segStart;
    const progress = segDur > 0 ? (current - segStart) / segDur : 1;
    const timeIn = current - segStart;
    const timeOut = segEnd - current;

    const ease = t => { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); };

    switch (type) {
        case 'fade':
            if (timeIn < animDur) state.opacity = ease(timeIn / animDur);
            else if (timeOut < animDur) state.opacity = ease(timeOut / animDur);
            break;

        case 'slide_up': {
            const d = frameH * 0.05;
            if (timeIn < animDur) { const t = ease(timeIn / animDur); state.offsetY = d * (1 - t); state.opacity = t; }
            else if (timeOut < animDur) { const t = ease(timeOut / animDur); state.offsetY = -d * (1 - t); state.opacity = t; }
            break;
        }

        case 'slide_down': {
            const d = frameH * 0.05;
            if (timeIn < animDur) { const t = ease(timeIn / animDur); state.offsetY = -d * (1 - t); state.opacity = t; }
            else if (timeOut < animDur) { const t = ease(timeOut / animDur); state.offsetY = d * (1 - t); state.opacity = t; }
            break;
        }

        case 'typewriter': {
            // Removed segment text dependency - approximate with progress
            state.visibleChars = Math.round(Math.min(progress / 0.8, 1.0) * 1000);
            break;
        }

        case 'karaoke':
            // Will be computed by caller based on word timings
            state.highlightIdx = -1;
            break;

        case 'pop':
            if (timeIn < animDur) { const t = ease(timeIn / animDur); state.scale = 0.5 + 0.5 * t; state.opacity = t; }
            else if (timeOut < animDur) { const t = ease(timeOut / animDur); state.scale = 0.5 + 0.5 * t; state.opacity = t; }
            break;
    }

    return state;
}
