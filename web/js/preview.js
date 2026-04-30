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
        this._dragMode = null;
        this._dragStartX = 0;
        this._dragStartY = 0;
        this._dragStartBBox = null;
        this._boxSelected = false;
        this._lastBBox = null;

        this.onClickOutside = null;
        this.onChange = null;

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

        this._lastBBox = null;

        if (!activeSeg) return;

        // Resolve per-segment position (fallback to track)
        const posX = activeSeg.position_x ?? track.position_x ?? 0.5;
        const posY = activeSeg.position_y ?? track.position_y ?? 0.9;

        // Resolve per-line animation (segment override → track)
        const segStart = activeSeg.words[0]?.start_time ?? 0;
        const segEnd = activeSeg.words[activeSeg.words.length - 1]?.end_time ?? 0;
        const lineAnimType = activeSeg.line_animation_type ?? activeSeg.animation_type ?? track.line_animation_type ?? track.animation_type ?? 'none';
        const lineAnimDur = activeSeg.line_animation_duration ?? activeSeg.animation_duration ?? track.line_animation_duration ?? track.animation_duration ?? 0.3;
        const animState = computeAnimState(lineAnimType, currentTime, segStart, segEnd, lineAnimDur, h);

        if (animState.opacity <= 0) return;

        // Resolve per-word animation (segment override → track)
        const wordAnimType = activeSeg.word_animation_type ?? track.word_animation_type ?? 'none';
        const wordAnimDur = activeSeg.word_animation_duration ?? track.word_animation_duration ?? 0.3;

        const scaleFactor = w / (this.video.videoWidth || 1920);

        // Route to word-by-word if any word has a non-standard marker OR word animation is active
        const hasNonStandard = activeSeg.words.some(word =>
            (word.marker && word.marker !== 'standard') || word.style_override
        );
        const needsWordByWord = hasNonStandard || wordAnimType !== 'none';

        if (needsWordByWord) {
            this.drawSegmentWordByWord(ctx, activeSeg, track, posX, posY, animState, wordAnimType, wordAnimDur, currentTime, scaleFactor, w, h);
        } else {
            this.drawSegmentUniform(ctx, activeSeg, track, posX, posY, animState, scaleFactor, w, h);
        }

        ctx.globalAlpha = 1;

        // Draw bounding box and handles LAST so they sit on top of the text
        if (activeSeg && this._boxSelected && this._lastBBox) {
            this._drawHandles(ctx, track, w, h, activeSeg, this._overrideDrawBBox || this._lastBBox);
        }
    }

    // ── Draggable Handles & Bounding Box ───────────────────────────────────────

    _drawHandles(ctx, track, w, h, activeSeg, bbox) {
        if (!bbox) return;
        const { lx, rx, ty, by } = bbox;

        ctx.save();
        ctx.strokeStyle = '#9b51e0'; // clean purple
        ctx.lineWidth = 1.5;
        
        // Bounding box
        ctx.beginPath();
        ctx.rect(lx, ty, rx - lx, by - ty);
        ctx.stroke();

        // Handles
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#9b51e0';
        ctx.lineWidth = 1.5;

        const handles = [
            { x: lx, y: ty }, { x: (lx+rx)/2, y: ty }, { x: rx, y: ty }, // Top
            { x: lx, y: (ty+by)/2 }, { x: rx, y: (ty+by)/2 }, // Middle
            { x: lx, y: by }, { x: (lx+rx)/2, y: by }, { x: rx, y: by } // Bottom
        ];

        for (const pt of handles) {
            ctx.beginPath();
            ctx.arc(pt.x, pt.y, 4.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
        }
        ctx.restore();
    }

    _bindHandleEvents() {
        const cvs = this.canvas;
        const HANDLE_RADIUS = 8;

        const getActiveSeg = () => {
            if (!this.subtitleTrack || !this.subtitleTrack.segments) return null;
            const currentTime = this.video.currentTime;
            for (const seg of this.subtitleTrack.segments) {
                const startTime = seg.words.length > 0 ? seg.words[0].start_time : 0;
                const endTime = seg.words.length > 0 ? seg.words[seg.words.length - 1].end_time : 0;
                if (currentTime >= startTime && currentTime <= endTime) return seg;
            }
            return null;
        };

        const hitTest = (clientX, clientY) => {
            if (!this._lastBBox) return null;
            const { lx, rx, ty, by } = this._lastBBox;
            const mx = (lx + rx) / 2;
            const my = (ty + by) / 2;

            if (this._boxSelected) {
                const dist = (x1, y1) => Math.sqrt((clientX - x1)**2 + (clientY - y1)**2);
                if (dist(lx, ty) <= HANDLE_RADIUS) return 'nw';
                if (dist(rx, ty) <= HANDLE_RADIUS) return 'ne';
                if (dist(lx, by) <= HANDLE_RADIUS) return 'sw';
                if (dist(rx, by) <= HANDLE_RADIUS) return 'se';
                if (dist(mx, ty) <= HANDLE_RADIUS) return 'n';
                if (dist(mx, by) <= HANDLE_RADIUS) return 's';
                if (dist(lx, my) <= HANDLE_RADIUS) return 'w';
                if (dist(rx, my) <= HANDLE_RADIUS) return 'e';
            }

            if (clientX >= lx && clientX <= rx && clientY >= ty && clientY <= by) {
                return 'center';
            }
            return null;
        };

        const getCursor = (mode) => {
            switch(mode) {
                case 'nw': case 'se': return 'nwse-resize';
                case 'ne': case 'sw': return 'nesw-resize';
                case 'n': case 's': return 'ns-resize';
                case 'w': case 'e': return 'ew-resize';
                case 'center': return 'move';
                default: return 'default';
            }
        };

        cvs.addEventListener('mousemove', (e) => {
            const rect = cvs.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            if (this._dragMode) {
                const seg = getActiveSeg();
                if (!seg) return;
                const target = (seg && !seg.apply_for_all) ? seg : this.subtitleTrack;
                
                const w = cvs.width;
                const h = cvs.height;
                const dx = x - this._dragStartX;
                const dy = y - this._dragStartY;

                let posX = target.position_x ?? this.subtitleTrack.position_x ?? 0.5;
                let posY = target.position_y ?? this.subtitleTrack.position_y ?? 0.9;
                let boxW = this.subtitleTrack.text_box_width ?? 0.8;

                const { lx, rx, ty, by } = this._dragStartBBox;
                let drawBBox = { ...this._dragStartBBox };

                if (this._dragMode === 'center') {
                    posX = Math.max(0.05, Math.min(0.95, (this._dragStartBBox.mx + dx) / w));
                    posY = Math.max(0.05, Math.min(0.95, (by + dy) / h));
                    drawBBox.lx += dx;
                    drawBBox.rx += dx;
                    drawBBox.ty += dy;
                    drawBBox.by += dy;
                } else {
                    if (this._dragMode.includes('w') || this._dragMode.includes('e')) {
                        const mx = this._dragStartBBox.mx;
                        let newHalfWidth = Math.abs(x - mx);
                        if (newHalfWidth < 25) newHalfWidth = 25;
                        boxW = Math.max(0.05, Math.min(1.0, (newHalfWidth * 2) / w));
                        posX = target.position_x ?? this.subtitleTrack.position_x ?? 0.5;
                        
                        drawBBox.lx = mx - newHalfWidth;
                        drawBBox.rx = mx + newHalfWidth;
                    }

                    if (this._dragMode.includes('n') || this._dragMode.includes('s')) {
                        posY = Math.max(0.05, Math.min(0.95, (by + dy) / h));
                        drawBBox.by = by + dy;
                        drawBBox.ty = drawBBox.by - (by - ty);
                    }
                }

                target.position_x = posX;
                target.position_y = posY;
                if (this._dragMode !== 'center' && this._dragMode !== 'n' && this._dragMode !== 's') {
                    this.subtitleTrack.text_box_width = boxW;
                }

                this._overrideDrawBBox = drawBBox;
                this.draw();
                this._overrideDrawBBox = null;
                if (this.onChange) this.onChange();
            } else {
                cvs.style.cursor = getCursor(hitTest(x, y));
            }
        });

        cvs.addEventListener('mousedown', (e) => {
            const rect = cvs.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const hit = hitTest(x, y);
            if (hit) {
                this._boxSelected = true;
                this._dragMode = hit;
                this._dragStartX = x;
                this._dragStartY = y;
                this._dragStartBBox = { ...this._lastBBox, mx: (this._lastBBox.lx + this._lastBBox.rx)/2 };
                this.draw();
                e.preventDefault();
            } else {
                if (this._boxSelected) {
                    this._boxSelected = false;
                    this.draw();
                } else if (this.onClickOutside) {
                    this.onClickOutside();
                }
            }
        });

        const stopDrag = () => {
            if (this._dragMode) {
                this._dragMode = null;
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

        let maxLineW = 0;
        for (let li = 0; li < lines.length; li++) {
            const metrics = ctx.measureText(lines[li]);
            if (metrics.width > maxLineW) maxLineW = metrics.width;
        }
        const pad = style.bg_color ? (style.bg_padding || 8) * scaleFactor : 4 * scaleFactor;
        const tightW = maxLineW + pad * 2;

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

        this._lastBBox = {
            lx: baseX - tightW / 2,
            rx: baseX + tightW / 2,
            ty: baseY,
            by: baseY + totalH
        };
    }

    // ── Word-by-word renderer (marker-aware, with wrapping + per-word animation) ──

    drawSegmentWordByWord(ctx, seg, track, posX, posY, animState, wordAnimType, wordAnimDur, currentTime, scaleFactor, w, h) {
        const segStyle = seg.style || track.global_style || {};
        const boxW = (track.text_box_width ?? 0.8) * w;

        ctx.textBaseline = 'top';

        // 1. Measure every word with its resolved style + compute per-word animation
        const wordInfos = seg.words.map((word, idx) => {
            const style = this.getWordStyle(word, segStyle, track);
            const fontSize = Math.round((style.font_size || 48) * scaleFactor);
            const fontStr = this.buildFontStr(style, fontSize);
            ctx.font = fontStr;
            const text = this.applyTextTransform(word.word, style.text_transform) + (idx < seg.words.length - 1 ? ' ' : '');
            const measured = ctx.measureText(text);

            // Per-word animation: word override > segment/track
            const wAnimType = word.word_animation_type ?? word.animation_type ?? wordAnimType;
            const wAnimDur = word.word_animation_duration ?? word.animation_duration ?? wordAnimDur;
            const wAnimState = computeWordAnimState(wAnimType, currentTime, word.start_time, word.end_time, wAnimDur, h);

            return { text, style, fontSize, fontStr, width: measured.width, word, wAnimState };
        });

        // 2. Group into lines
        const lines = [];
        let currentLine = [];
        let currentLineW = 0;
        let maxLineW = 0;

        for (const info of wordInfos) {
            if (currentLine.length > 0 && currentLineW + info.width > boxW) {
                lines.push(currentLine);
                if (currentLineW > maxLineW) maxLineW = currentLineW;
                currentLine = [info];
                currentLineW = info.width;
            } else {
                currentLine.push(info);
                currentLineW += info.width;
            }
        }
        if (currentLine.length > 0) {
            lines.push(currentLine);
            if (currentLineW > maxLineW) maxLineW = currentLineW;
        }

        const tightW = maxLineW + 8 * scaleFactor;

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
                const { text, style, fontSize, fontStr, width: ww, wAnimState } = info;
                const lineH = fontSize * (style.line_height ?? 1.2);

                // Skip invisible words (e.g., typewriter: not yet revealed)
                if (!wAnimState.visible) {
                    curX += ww;
                    continue;
                }

                const wordOpacity = wAnimState.opacity;
                const wordOffsetX = wAnimState.offsetX;
                const wordOffsetY = wAnimState.offsetY;

                const drawX = curX + wordOffsetX;
                const drawY = ly + wordOffsetY;

                ctx.font = fontStr;
                ctx.globalAlpha = animState.opacity * wordOpacity * (style.text_opacity ?? 1);

                if (ctx.globalAlpha <= 0) {
                    curX += ww;
                    continue;
                }

                // Background
                if (style.bg_color) {
                    ctx.fillStyle = style.bg_color;
                    const pad = (style.bg_padding || 8) * scaleFactor;
                    ctx.fillRect(drawX - pad, drawY - pad, ww + 2 * pad, lineH + 2 * pad);
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
                    ctx.fillText(text, drawX, drawY);
                    ctx.restore();
                }

                // Stroke
                if (style.stroke_enabled !== false && style.outline_color && style.outline_width > 0) {
                    ctx.strokeStyle = style.outline_color;
                    ctx.lineWidth = style.outline_width * scaleFactor * 2;
                    ctx.lineJoin = 'round';
                    ctx.strokeText(text, drawX, drawY);
                }

                // Fill — karaoke highlight changes fill color
                if (wAnimState.isHighlighted) {
                    ctx.fillStyle = '#FFD700';  // Karaoke highlight color
                } else {
                    ctx.fillStyle = this.buildFillStyle(ctx, style, drawX, drawY, ww, lineH, scaleFactor);
                }
                ctx.fillText(text, drawX, drawY);

                curX += ww;
            }
        }

        ctx.globalAlpha = 1;

        this._lastBBox = {
            lx: baseX - tightW / 2,
            rx: baseX + tightW / 2,
            ty: baseY,
            by: baseY + totalH
        };
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

    /**
     * Compute exact word positions at video resolution for export.
     * Uses an offscreen canvas at the actual video dimensions so that
     * ctx.measureText() produces pixel-perfect widths matching the preview.
     * Returns an array of per-segment layout objects.
     */
    computeExportLayout(track, videoW, videoH) {
        // Create offscreen canvas at video resolution
        const offscreen = document.createElement('canvas');
        offscreen.width = videoW;
        offscreen.height = videoH;
        const ctx = offscreen.getContext('2d');
        ctx.textBaseline = 'top';

        // scaleFactor = 1 since we're rendering at video resolution
        const scaleFactor = 1;
        const segmentLayouts = [];

        for (const seg of track.segments) {
            const segStyle = seg.style || track.global_style || {};
            const boxW = (track.text_box_width ?? 0.8) * videoW;
            const posX = seg.position_x ?? track.position_x ?? 0.5;
            const posY = seg.position_y ?? track.position_y ?? 0.9;

            // Check if this segment needs word-by-word
            const hasNonStandard = seg.words.some(w =>
                (w.marker && w.marker !== 'standard') || w.style_override
            );
            const wordAnimType = seg.word_animation_type ?? track.word_animation_type ?? 'none';
            const needsWordByWord = hasNonStandard || wordAnimType !== 'none';

            if (needsWordByWord) {
                // Word-by-word layout
                const wordLayouts = [];
                const wordInfos = seg.words.map((word, idx) => {
                    const style = this.getWordStyle(word, segStyle, track);
                    const fontSize = Math.round((style.font_size || 48) * scaleFactor);
                    const fontStr = this.buildFontStr(style, fontSize);
                    ctx.font = fontStr;
                    const text = this.applyTextTransform(word.word, style.text_transform) + (idx < seg.words.length - 1 ? ' ' : '');
                    const measured = ctx.measureText(text);
                    return { text, style, fontSize, fontStr, width: measured.width, wordIdx: idx };
                });

                // Group into lines
                const lines = [];
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

                const baseLineH = (segStyle.font_size || 48) * scaleFactor * (segStyle.line_height ?? 1.2);
                const totalH = baseLineH * lines.length;
                const baseX = posX * videoW;
                const baseY = posY * videoH - totalH;

                for (let li = 0; li < lines.length; li++) {
                    const line = lines[li];
                    const lineW = line.reduce((s, info) => s + info.width, 0);
                    let curX = baseX - lineW / 2;
                    const ly = baseY + li * baseLineH;

                    for (const info of line) {
                        wordLayouts.push({
                            word_idx: info.wordIdx,
                            x: curX,
                            y: ly,
                            width: info.width,
                            line_height: baseLineH,
                        });
                        curX += info.width;
                    }
                }

                segmentLayouts.push({
                    seg_idx: track.segments.indexOf(seg),
                    mode: 'word_by_word',
                    words: wordLayouts,
                    base_line_h: (segStyle.font_size || 48) * (segStyle.line_height ?? 1.2),
                });
            } else {
                // Uniform layout
                const style = segStyle;
                const fontSize = Math.round((style.font_size || 48) * scaleFactor);
                const fontStr = this.buildFontStr(style, fontSize);
                ctx.font = fontStr;

                const fullText = this.applyTextTransform(
                    seg.words.map(w => w.word).join(' '),
                    style.text_transform
                );
                const lines = this._wrapText(ctx, fullText, boxW);
                const lineH = fontSize * (style.line_height ?? 1.2);
                const totalH = lineH * lines.length;
                const baseX = posX * videoW;
                const baseY = posY * videoH - totalH;

                const lineLayouts = [];
                for (let li = 0; li < lines.length; li++) {
                    const lineText = lines[li];
                    const metrics = ctx.measureText(lineText);
                    const lineW = metrics.width;
                    const lx = baseX - lineW / 2;
                    const ly = baseY + li * lineH;
                    lineLayouts.push({
                        text: lineText,
                        x: lx,
                        y: ly,
                        width: lineW,
                        line_height: lineH,
                    });
                }

                segmentLayouts.push({
                    seg_idx: track.segments.indexOf(seg),
                    mode: 'uniform',
                    lines: lineLayouts,
                    base_line_h: lineH,
                });
            }
        }

        return segmentLayouts;
    }
}


// ── Line Animation State ────────────────────────────────────────────────────

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
            // Legacy line-level typewriter (kept for backwards compat)
            state.visibleChars = Math.round(Math.min(progress / 0.8, 1.0) * 1000);
            break;

        case 'pop':
            if (timeIn < animDur) { const t = ease(timeIn / animDur); state.scale = 0.5 + 0.5 * t; state.opacity = t; }
            else if (timeOut < animDur) { const t = ease(timeOut / animDur); state.scale = 0.5 + 0.5 * t; state.opacity = t; }
            break;
    }

    return state;
}


// ── Per-Word Animation State ────────────────────────────────────────────────

function computeWordAnimState(type, current, wordStart, wordEnd, animDur, frameH) {
    const state = { opacity: 1, offsetX: 0, offsetY: 0, scale: 1, visible: true, isHighlighted: false };

    if (type === 'none') return state;

    const ease = t => { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); };
    const timeSinceStart = current - wordStart;

    if (type === 'typewriter') {
        // Word invisible until its start_time
        if (current < wordStart) {
            state.visible = false;
            state.opacity = 0;
        } else {
            state.visible = true;
            state.opacity = 1;
        }
        return state;
    }

    if (type === 'karaoke') {
        // All words visible; current word is highlighted
        state.visible = true;
        state.isHighlighted = (wordStart <= current && current <= wordEnd);
        state.opacity = 1;
        return state;
    }

    // For all other types: word animates in at its start_time
    if (current < wordStart) {
        state.opacity = 0;
        state.visible = false;
        if (type === 'slide_up') state.offsetY = frameH * 0.03;
        else if (type === 'slide_down') state.offsetY = -frameH * 0.03;
        else if (type === 'pop') state.scale = 0.5;
        return state;
    }

    state.visible = true;

    if (timeSinceStart < animDur) {
        const t = ease(timeSinceStart / animDur);

        if (type === 'fade') {
            state.opacity = t;
        } else if (type === 'slide_up') {
            const d = frameH * 0.03;
            state.offsetY = d * (1 - t);
            state.opacity = t;
        } else if (type === 'slide_down') {
            const d = frameH * 0.03;
            state.offsetY = -d * (1 - t);
            state.opacity = t;
        } else if (type === 'pop') {
            state.scale = 0.5 + 0.5 * t;
            state.opacity = t;
        }
    }

    return state;
}
