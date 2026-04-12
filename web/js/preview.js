/**
 * OWN — Canvas-based subtitle preview overlay.
 * Renders subtitles on a <canvas> overlaying the <video> element.
 * Features:
 *  - word-by-word marker rendering (standard / highlight / spotlight)
 *  - text_box_width wrapping
 *  - draggable right-edge handle for text_box_width adjustment
 */

class SubtitlePreview {
    constructor(videoEl, canvasEl) {
        this.video = videoEl;
        this.canvas = canvasEl;
        this.ctx = canvasEl.getContext('2d');
        this.subtitleTrack = null;
        this.animationFrame = null;

        // --- Draggable text-box handle state ---
        this._handleDragging = false;
        this._handleCursor = 'ew-resize';

        this._bindHandleEvents();
    }

    setTrack(trackData) {
        this.subtitleTrack = trackData;
    }

    /** Call when text_box_width changes so handle moves immediately. */
    onWidthChange(cb) {
        this._onWidthChange = cb;
    }

    start() { this.render(); }

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

    // ── Core draw ──────────────────────────────────────────────────────────────

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

        // Draw handle only when a subtitle is visible
        if (activeSeg) {
            this._drawHandle(ctx, track, w, h);
        }

        if (!activeSeg) return;

        const posX = track.position_x ?? 0.5;
        const posY = track.position_y ?? 0.9;

        // Compute animation state
        const segStart = activeSeg.words[0]?.start_time ?? 0;
        const segEnd = activeSeg.words[activeSeg.words.length - 1]?.end_time ?? 0;
        const animType = track.animation_type || 'none';
        const animDur = track.animation_duration ?? 0.3;
        const animState = computeAnimState(animType, currentTime, segStart, segEnd, animDur, h);

        if (animState.opacity <= 0) return;

        const scaleFactor = w / (this.video.videoWidth || 1920);

        // Route to word-by-word if any word has a non-standard marker
        const hasNonStandard = activeSeg.words.some(word =>
            (word.marker && word.marker !== 'standard') || word.style_override
        );

        if (hasNonStandard) {
            this.drawSegmentWordByWord(ctx, activeSeg, track, posX, posY, animState, scaleFactor, w, h);
        } else {
            this.drawSegmentUniform(ctx, activeSeg, track, posX, posY, animState, scaleFactor, w, h);
        }

        ctx.globalAlpha = 1;
    }

    // ── Draggable handle ───────────────────────────────────────────────────────

    _getHandleX(track, w) {
        const boxWidth = track.text_box_width ?? 0.8;
        const posX = track.position_x ?? 0.5;
        const halfBox = boxWidth * w / 2;
        return posX * w + halfBox;
    }

    _drawHandle(ctx, track, w, h) {
        const hx = this._getHandleX(track, w);
        const lineTop = h * 0.05;
        const lineBottom = h * 0.95;

        ctx.save();
        ctx.setLineDash([6, 5]);
        ctx.strokeStyle = 'rgba(255,255,255,0.55)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(hx, lineTop);
        ctx.lineTo(hx, lineBottom);
        ctx.stroke();

        // Grip circle
        const cy = h * 0.5;
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.beginPath();
        ctx.arc(hx, cy, 8, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,0.4)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Grip chevrons
        ctx.strokeStyle = 'rgba(60,60,60,0.9)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(hx - 3, cy - 4); ctx.lineTo(hx - 6, cy); ctx.lineTo(hx - 3, cy + 4);
        ctx.moveTo(hx + 3, cy - 4); ctx.lineTo(hx + 6, cy); ctx.lineTo(hx + 3, cy + 4);
        ctx.stroke();

        ctx.restore();
    }

    _bindHandleEvents() {
        const cvs = this.canvas;

        const hitTest = (clientX) => {
            if (!this.subtitleTrack) return false;
            const rect = cvs.getBoundingClientRect();
            const x = clientX - rect.left;
            const w = cvs.width;
            const hx = this._getHandleX(this.subtitleTrack, w);
            return Math.abs(x - hx) <= 12;
        };

        cvs.addEventListener('mousemove', (e) => {
            if (this._handleDragging) {
                // Update text_box_width
                const rect = cvs.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const w = cvs.width;
                const track = this.subtitleTrack;
                const posX = (track.position_x ?? 0.5) * w;
                const newHalfBox = x - posX;
                const newWidth = Math.max(0.1, Math.min(1.0, (newHalfBox * 2) / w));
                track.text_box_width = newWidth;
                if (this._onWidthChange) this._onWidthChange(newWidth);
            } else {
                cvs.style.cursor = hitTest(e.clientX) ? this._handleCursor : 'default';
            }
        });

        cvs.addEventListener('mousedown', (e) => {
            if (hitTest(e.clientX)) {
                this._handleDragging = true;
                e.preventDefault();
            }
        });

        const stopDrag = () => {
            if (this._handleDragging) {
                this._handleDragging = false;
                if (this._onWidthChange) this._onWidthChange(this.subtitleTrack?.text_box_width);
            }
        };
        cvs.addEventListener('mouseup', stopDrag);
        window.addEventListener('mouseup', stopDrag);
    }

    // ── Uniform renderer (all words same style, with wrapping) ─────────────────

    drawSegmentUniform(ctx, seg, track, posX, posY, animState, scaleFactor, w, h) {
        const style = seg.style || track.global_style || {};
        const boxW = (track.text_box_width ?? 0.8) * w;

        let fullText = seg.words.map(wd => wd.word).join(' ');
        fullText = this.applyTextTransform(fullText, style.text_transform);

        if (animState.visibleChars >= 0) {
            fullText = fullText.substring(0, animState.visibleChars);
        }
        if (!fullText.trim()) return;

        const fontSize = Math.round((style.font_size || 48) * scaleFactor);
        const fontStr = this.buildFontStr(style, fontSize);
        ctx.font = fontStr;
        ctx.textBaseline = 'top';

        // Word-wrap
        const lines = this._wrapText(ctx, fullText, boxW);

        const lineHeightMult = style.line_height ?? 1.2;
        const lineH = fontSize * lineHeightMult;
        const totalH = lineH * lines.length;

        const baseX = posX * w;
        const baseY = posY * h - totalH + (animState.offsetY ?? 0);

        ctx.globalAlpha = animState.opacity * (style.text_opacity ?? 1);

        const rotation = (style.rotation || 0) * Math.PI / 180;
        if (rotation !== 0) {
            ctx.save();
            ctx.translate(baseX, baseY + totalH / 2);
            ctx.rotate(rotation);
            ctx.translate(-baseX, -(baseY + totalH / 2));
        }

        for (let li = 0; li < lines.length; li++) {
            const lineText = lines[li];
            if (!lineText.trim()) continue;

            const metrics = ctx.measureText(lineText);
            const lineW = metrics.width;
            const lx = baseX - lineW / 2 + (animState.offsetX ?? 0);
            const ly = baseY + li * lineH;

            // Background
            if (style.bg_color) {
                ctx.fillStyle = style.bg_color;
                const pad = (style.bg_padding || 8) * scaleFactor;
                ctx.fillRect(lx - pad, ly - pad, lineW + 2 * pad, lineH + 2 * pad);
            }

            // Shadow (hard offset)
            if (style.shadow_enabled !== false && style.shadow_color &&
                (style.shadow_offset_x || style.shadow_offset_y || style.shadow_blur)) {
                ctx.save();
                ctx.shadowColor = style.shadow_color;
                ctx.shadowBlur = (style.shadow_blur || 0) * scaleFactor;
                ctx.shadowOffsetX = (style.shadow_offset_x || 0) * scaleFactor;
                ctx.shadowOffsetY = (style.shadow_offset_y || 0) * scaleFactor;
                ctx.fillStyle = style.text_color || '#FFFFFF';
                ctx.fillText(lineText, lx, ly);
                ctx.restore();
            }

            // Stroke
            if (style.stroke_enabled !== false && style.outline_color && style.outline_width > 0) {
                ctx.strokeStyle = style.outline_color;
                ctx.lineWidth = style.outline_width * scaleFactor * 2;
                ctx.lineJoin = 'round';
                ctx.strokeText(lineText, lx, ly);
            }

            // Fill
            ctx.fillStyle = this.buildFillStyle(ctx, style, lx, ly, lineW, lineH, scaleFactor);
            ctx.fillText(lineText, lx, ly);
        }

        if (rotation !== 0) ctx.restore();
    }

    // ── Word-by-word renderer (marker-aware, with wrapping) ────────────────────

    drawSegmentWordByWord(ctx, seg, track, posX, posY, animState, scaleFactor, w, h) {
        const segStyle = seg.style || track.global_style || {};
        const boxW = (track.text_box_width ?? 0.8) * w;

        ctx.textBaseline = 'top';

        // 1. Measure every word with its resolved style
        const wordInfos = seg.words.map((word, idx) => {
            const style = this.getWordStyle(word, segStyle, track);
            const fontSize = Math.round((style.font_size || 48) * scaleFactor);
            const fontStr = this.buildFontStr(style, fontSize);
            ctx.font = fontStr;
            const text = this.applyTextTransform(word.word, style.text_transform) + (idx < seg.words.length - 1 ? ' ' : '');
            const measured = ctx.measureText(text);
            return { text, style, fontSize, fontStr, width: measured.width };
        });

        // 2. Group into lines
        const lines = [];  // each line: [ wordInfo, ... ]
        let currentLine = [];
        let currentLineW = 0;

        for (const info of wordInfos) {
            if (currentLine.length > 0 && currentLineW + info.width > boxW) {
                lines.push(currentLine);
                currentLine = [info];
                currentLineW = info.width;
            } else {
                currentLine.push(info);
                currentLineW += info.width;
            }
        }
        if (currentLine.length > 0) lines.push(currentLine);

        // 3. Compute total block height using base segment style line height
        const baseLineH = (segStyle.font_size || 48) * scaleFactor * (segStyle.line_height ?? 1.2);
        const totalH = baseLineH * lines.length;

        const baseX = posX * w;
        const baseY = posY * h - totalH + (animState.offsetY ?? 0);

        // 4. Draw line by line, word by word
        for (let li = 0; li < lines.length; li++) {
            const line = lines[li];
            const lineW = line.reduce((s, info) => s + info.width, 0);
            let curX = baseX - lineW / 2 + (animState.offsetX ?? 0);
            const ly = baseY + li * baseLineH;

            for (const info of line) {
                const { text, style, fontSize, fontStr, width: ww } = info;
                const lineH = fontSize * (style.line_height ?? 1.2);

                ctx.font = fontStr;
                ctx.globalAlpha = animState.opacity * (style.text_opacity ?? 1);

                // Background
                if (style.bg_color) {
                    ctx.fillStyle = style.bg_color;
                    const pad = (style.bg_padding || 8) * scaleFactor;
                    ctx.fillRect(curX - pad, ly - pad, ww + 2 * pad, lineH + 2 * pad);
                }

                // Shadow
                if (style.shadow_enabled !== false && style.shadow_color &&
                    (style.shadow_offset_x || style.shadow_offset_y || style.shadow_blur)) {
                    ctx.save();
                    ctx.shadowColor = style.shadow_color;
                    ctx.shadowBlur = (style.shadow_blur || 0) * scaleFactor;
                    ctx.shadowOffsetX = (style.shadow_offset_x || 0) * scaleFactor;
                    ctx.shadowOffsetY = (style.shadow_offset_y || 0) * scaleFactor;
                    ctx.fillStyle = style.text_color || '#FFFFFF';
                    ctx.fillText(text, curX, ly);
                    ctx.restore();
                }

                // Stroke
                if (style.stroke_enabled !== false && style.outline_color && style.outline_width > 0) {
                    ctx.strokeStyle = style.outline_color;
                    ctx.lineWidth = style.outline_width * scaleFactor * 2;
                    ctx.lineJoin = 'round';
                    ctx.strokeText(text, curX, ly);
                }

                // Fill
                ctx.fillStyle = this.buildFillStyle(ctx, style, curX, ly, ww, lineH, scaleFactor);
                ctx.fillText(text, curX, ly);

                curX += ww;
            }
        }

        ctx.globalAlpha = 1;
    }

    // ── Style resolution ───────────────────────────────────────────────────────

    /**
     * Resolve word style following the marker system:
     *   1. style_override (individual per-word)
     *   2. marker='highlight' → track.highlight_style
     *   3. marker='spotlight' → track.spotlight_style
     *   4. segment style
     */
    getWordStyle(word, segStyle, track) {
        if (word.style_override) return word.style_override;

        const marker = word.marker || 'standard';
        if (marker === 'highlight' && track.highlight_style) return track.highlight_style;
        if (marker === 'spotlight' && track.spotlight_style) return track.spotlight_style;

        return segStyle;
    }

    // ── Text wrapping helper ───────────────────────────────────────────────────

    _wrapText(ctx, text, maxWidth) {
        const words = text.split(' ');
        const lines = [];
        let current = '';

        for (const word of words) {
            const test = current ? current + ' ' + word : word;
            if (current && ctx.measureText(test).width > maxWidth) {
                lines.push(current);
                current = word;
            } else {
                current = test;
            }
        }
        if (current) lines.push(current);
        return lines.length > 0 ? lines : [''];
    }

    // ── Helpers ────────────────────────────────────────────────────────────────

    buildFontStr(style, fontSize) {
        const weight = style.font_weight || (style.bold ? 700 : 400);
        const fontStyle = style.font_style || (style.italic ? 'italic' : 'normal');
        return `${fontStyle} ${weight} ${fontSize}px "${style.font_family || 'sans-serif'}"`;
    }

    applyTextTransform(text, transform) {
        switch (transform) {
            case 'uppercase':  return text.toUpperCase();
            case 'lowercase':  return text.toLowerCase();
            case 'capitalize': return text.replace(/\b\w/g, c => c.toUpperCase());
            default:           return text;
        }
    }

    buildFillStyle(ctx, style, x, y, textW, textH, scaleFactor) {
        if (style.fill_type === 'gradient') {
            const angle = (style.gradient_angle || 0) * Math.PI / 180;
            const c1 = style.gradient_color1 || '#FFFFFF';
            const c2 = style.gradient_color2 || '#FFD700';

            if (style.gradient_type === 'radial') {
                const cx = x + textW / 2;
                const cy = y + textH / 2;
                const r = Math.max(textW, textH) / 2;
                const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
                grad.addColorStop(0, c1);
                grad.addColorStop(1, c2);
                return grad;
            } else {
                const dx = Math.cos(angle) * textW / 2;
                const dy = Math.sin(angle) * textH / 2;
                const cx = x + textW / 2;
                const cy = y + textH / 2;
                const grad = ctx.createLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy);
                grad.addColorStop(0, c1);
                grad.addColorStop(1, c2);
                return grad;
            }
        }
        return style.text_color || '#FFFFFF';
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

        case 'typewriter':
            state.visibleChars = Math.round(Math.min(progress / 0.8, 1.0) * 1000);
            break;

        case 'pop':
            if (timeIn < animDur) { const t = ease(timeIn / animDur); state.scale = 0.5 + 0.5 * t; state.opacity = t; }
            else if (timeOut < animDur) { const t = ease(timeOut / animDur); state.scale = 0.5 + 0.5 * t; state.opacity = t; }
            break;
    }

    return state;
}
