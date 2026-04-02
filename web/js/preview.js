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

        const posX = track.position_x || 0.5;
        const posY = track.position_y || 0.9;

        // Compute animation state
        const segStart = activeSeg.words[0]?.start_time || 0;
        const segEnd = activeSeg.words[activeSeg.words.length - 1]?.end_time || 0;
        const animType = track.animation_type || 'none';
        const animDur = track.animation_duration || 0.3;
        const animState = computeAnimState(animType, currentTime, segStart, segEnd, animDur, h);

        if (animState.opacity <= 0) return;

        // Scale font size based on canvas vs actual resolution
        const scaleFactor = w / (this.video.videoWidth || 1920);

        // Check if any words have special styling
        const hasSpecialWords = activeSeg.words.some(w => w.is_special);

        if (hasSpecialWords) {
            // Render each word individually with its own style
            this.drawSegmentWithWordStyles(ctx, activeSeg, track, posX, posY, animState, scaleFactor, w, h);
        } else {
            // Render entire segment with segment style
            this.drawSegmentUniform(ctx, activeSeg, track, posX, posY, animState, scaleFactor, w, h);
        }

        ctx.globalAlpha = 1;
    }

    drawSegmentUniform(ctx, seg, track, posX, posY, animState, scaleFactor, w, h) {
        const style = seg.style || track.global_style || {};

        // Build display text with text transform
        let displayText = seg.words.map(w => w.word).join(' ');
        displayText = this.applyTextTransform(displayText, style.text_transform);

        if (animState.visibleChars >= 0) {
            displayText = displayText.substring(0, animState.visibleChars);
        }

        if (!displayText.trim()) return;

        const fontSize = Math.round((style.font_size || 48) * scaleFactor);
        const fontStr = this.buildFontStr(style, fontSize);
        ctx.font = fontStr;
        ctx.textBaseline = 'top';

        // Adjust for letter spacing
        const letterSpacing = (style.letter_spacing || 0) * scaleFactor;
        ctx.letterSpacing = `${letterSpacing}px`;

        const metrics = ctx.measureText(displayText);
        const textW = metrics.width;
        const lineHeight = style.line_height || 1.2;
        const textH = fontSize * lineHeight;

        let x = posX * w - textW / 2;
        let y = posY * h - textH;

        x += (animState.offsetX || 0) * scaleFactor;
        y += (animState.offsetY || 0) * scaleFactor;

        x = Math.max(0, Math.min(x, w - textW));
        y = Math.max(0, Math.min(y, h - textH));

        // Apply text opacity
        const textOpacity = style.text_opacity ?? 1;
        ctx.globalAlpha = animState.opacity * textOpacity;

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
        if (style.shadow_enabled !== false && style.shadow_color && (style.shadow_offset_x || style.shadow_offset_y || style.shadow_blur)) {
            ctx.save();
            if (style.shadow_blur) {
                ctx.shadowColor = style.shadow_color;
                ctx.shadowBlur = (style.shadow_blur || 0) * scaleFactor;
                ctx.shadowOffsetX = (style.shadow_offset_x || 0) * scaleFactor;
                ctx.shadowOffsetY = (style.shadow_offset_y || 0) * scaleFactor;
            } else {
                ctx.fillStyle = style.shadow_color;
            }
            if (!style.shadow_blur) {
                ctx.fillText(displayText,
                    x + (style.shadow_offset_x || 0) * scaleFactor,
                    y + (style.shadow_offset_y || 0) * scaleFactor
                );
            } else {
                ctx.fillStyle = style.shadow_color;
                ctx.fillText(displayText, x, y);
            }
            ctx.restore();
        }

        // Outline / Stroke
        if (style.stroke_enabled !== false && style.outline_color && style.outline_width > 0) {
            ctx.strokeStyle = style.outline_color;
            ctx.lineWidth = style.outline_width * scaleFactor * 2;
            ctx.lineJoin = 'round';
            ctx.strokeText(displayText, x, y);
        }

        // Karaoke highlight
        if (animState.highlightIdx >= 0) {
            this.drawKaraoke(ctx, seg, style, animState, x, y, fontSize, scaleFactor);
        } else {
            // Main text fill (solid or gradient)
            ctx.fillStyle = this.buildFillStyle(ctx, style, x, y, textW, textH, scaleFactor);
            ctx.fillText(displayText, x, y);
        }

        // Reset letter spacing
        ctx.letterSpacing = '0px';

        if (rotationAngle !== 0) {
            ctx.restore();
        }
    }

    drawSegmentWithWordStyles(ctx, seg, track, posX, posY, animState, scaleFactor, w, h) {
        const globalStyle = track.global_style || {};
        const segStyle = seg.style || globalStyle;

        // Calculate total text width for positioning
        let totalWidth = 0;
        const wordWidths = [];

        seg.words.forEach(word => {
            const style = this.getWordStyle(word, segStyle, globalStyle, track);
            const fontSize = Math.round((style.font_size || 48) * scaleFactor);
            const fontStr = this.buildFontStr(style, fontSize);
            ctx.font = fontStr;
            const letterSpacing = (style.letter_spacing || 0) * scaleFactor;
            ctx.letterSpacing = `${letterSpacing}px`;
            const wordText = this.applyTextTransform(word.word, style.text_transform) + ' ';
            const metrics = ctx.measureText(wordText);
            wordWidths.push(metrics.width);
            totalWidth += metrics.width;
        });

        // Starting X position
        let currentX = posX * w - totalWidth / 2;
        currentX += (animState.offsetX || 0) * scaleFactor;

        // Y position
        const baseFontSize = Math.round((segStyle.font_size || 48) * scaleFactor);
        const lineHeight = segStyle.line_height || 1.2;
        let currentY = posY * h - baseFontSize * lineHeight;
        currentY += (animState.offsetY || 0) * scaleFactor;

        ctx.textBaseline = 'top';

        // Render each word
        seg.words.forEach((word, idx) => {
            const style = this.getWordStyle(word, segStyle, globalStyle, track);
            const fontSize = Math.round((style.font_size || 48) * scaleFactor);
            let wordText = this.applyTextTransform(word.word, style.text_transform) + ' ';

            // Set font for this word
            const fontStr = this.buildFontStr(style, fontSize);
            ctx.font = fontStr;
            const letterSpacing = (style.letter_spacing || 0) * scaleFactor;
            ctx.letterSpacing = `${letterSpacing}px`;

            const wordW = wordWidths[idx];
            const wordLineHeight = style.line_height || 1.2;
            const wordH = fontSize * wordLineHeight;

            const textOpacity = style.text_opacity ?? 1;
            ctx.globalAlpha = animState.opacity * textOpacity;

            // Rotation
            const rotationAngle = (style.rotation || 0) * Math.PI / 180;
            if (rotationAngle !== 0) {
                ctx.save();
                ctx.translate(currentX + wordW / 2, currentY + wordH / 2);
                ctx.rotate(rotationAngle);
                ctx.translate(-(currentX + wordW / 2), -(currentY + wordH / 2));
            }

            // Background
            if (style.bg_color) {
                ctx.fillStyle = style.bg_color;
                const pad = (style.bg_padding || 8) * scaleFactor;
                ctx.fillRect(currentX - pad, currentY - pad, wordW + 2 * pad, wordH + 2 * pad);
            }

            // Shadow
            if (style.shadow_enabled !== false && style.shadow_color && (style.shadow_offset_x || style.shadow_offset_y || style.shadow_blur)) {
                ctx.save();
                if (style.shadow_blur) {
                    ctx.shadowColor = style.shadow_color;
                    ctx.shadowBlur = (style.shadow_blur || 0) * scaleFactor;
                    ctx.shadowOffsetX = (style.shadow_offset_x || 0) * scaleFactor;
                    ctx.shadowOffsetY = (style.shadow_offset_y || 0) * scaleFactor;
                    ctx.fillStyle = style.shadow_color;
                    ctx.fillText(wordText, currentX, currentY);
                } else {
                    ctx.fillStyle = style.shadow_color;
                    ctx.fillText(wordText,
                        currentX + (style.shadow_offset_x || 0) * scaleFactor,
                        currentY + (style.shadow_offset_y || 0) * scaleFactor
                    );
                }
                ctx.restore();
            }

            // Outline / Stroke
            if (style.stroke_enabled !== false && style.outline_color && style.outline_width > 0) {
                ctx.strokeStyle = style.outline_color;
                ctx.lineWidth = style.outline_width * scaleFactor * 2;
                ctx.lineJoin = 'round';
                ctx.strokeText(wordText, currentX, currentY);
            }

            // Main text fill
            ctx.fillStyle = this.buildFillStyle(ctx, style, currentX, currentY, wordW, wordH, scaleFactor);
            ctx.fillText(wordText, currentX, currentY);

            // Reset letter spacing
            ctx.letterSpacing = '0px';

            if (rotationAngle !== 0) {
                ctx.restore();
            }

            currentX += wordW;
        });
    }

    getWordStyle(word, segStyle, globalStyle, track) {
        // If word has individual style override, use it
        if (word.style_override) {
            return word.style_override;
        }

        // If word is in a group, use group style
        if (word.group_id && track.special_groups && track.special_groups[word.group_id]) {
            return track.special_groups[word.group_id].style;
        }

        // Otherwise use segment style
        return segStyle;
    }

    drawKaraoke(ctx, seg, style, animState, baseX, baseY, fontSize, scale) {
        let curX = baseX;
        seg.words.forEach((word, idx) => {
            const text = this.applyTextTransform(word.word, style.text_transform) + ' ';
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

    // Build font string from style
    buildFontStr(style, fontSize) {
        const weight = style.font_weight || 400;
        const fontStyle = style.font_style || 'normal';
        // Backwards compat: legacy bold/italic
        const legacyWeight = style.bold ? 'bold' : weight;
        const legacyStyle = style.italic ? 'italic' : fontStyle;
        return `${legacyStyle} ${legacyWeight} ${fontSize}px "${style.font_family || 'sans-serif'}"`;
    }

    // Apply text transform
    applyTextTransform(text, transform) {
        switch (transform) {
            case 'uppercase': return text.toUpperCase();
            case 'lowercase': return text.toLowerCase();
            case 'capitalize': return text.replace(/\b\w/g, c => c.toUpperCase());
            default: return text;
        }
    }

    // Build fill style (solid color or gradient)
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
                // Linear gradient
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
