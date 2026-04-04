# Code Context: Style Engine

## Last Updated
2025-04-02

## Description
Comprehensive text styling system supporting 6 categories: Font, Fill, Stroke, Shadow, Spacing, Opacity. Supports both global (All) and per-word (Specials) styling. Video-level settings are in a separate tab.

## Files

### models/subtitle.py — SubtitleStyle dataclass
- `font_weight` (int, default 400): CSS font weight 100–900
- `font_style` (str, default 'normal'): normal / italic / oblique
- `text_transform` (str, default 'none'): none / uppercase / lowercase / capitalize
- `fill_type` (str, default 'solid'): solid / gradient
- `gradient_color1`, `gradient_color2`: hex color strings for gradient stops
- `gradient_angle` (int, default 0): degrees for linear gradient direction
- `gradient_type` (str, default 'linear'): linear / radial
- `stroke_enabled` (bool, default True): toggle stroke rendering
- `shadow_enabled` (bool, default True): toggle shadow rendering
- `shadow_blur` (int, default 0): gaussian blur radius for shadow
- `letter_spacing` (float, default 0): px spacing between letters
- `word_spacing` (float, default 0): px spacing between words
- `line_height` (float, default 1.2): line height multiplier
- `text_opacity` (float, default 1.0): 0.0–1.0 opacity

### web/editor.html — Style Panel Structure
- Top-level tabs: Style / Video / Presets (data-main-tab)
- Sub-tabs: All / Specials (data-sub-tab)
- 6 collapsible `<details>` groups per subsection (Font, Fill, Stroke, Shadow, Spacing, Opacity)
- ID convention: `{prefix}-{property}` where prefix = global | special

### web/js/editor.js — Control Bindings
- `initGlobalStyleControls()`: binds all global-* controls → updateGlobalStyle()
- `initSpecialStyleControls()`: binds all special-* controls → updateSpecialStyle()
- `applyTrackToControls(track)`: populates UI from track data
- `loadSpecialStyle()`: populates special controls from selected word style
- `toggleFillControls(prefix, fillType)`: show/hide solid vs gradient controls
- `toggleStrokeControls(prefix, enabled)`: enable/disable stroke sub-controls
- `toggleShadowControls(prefix, enabled)`: enable/disable shadow sub-controls

### web/js/preview.js — Canvas Rendering
- `buildFontStr(style, fontSize)`: builds CSS font string from font_weight + font_style
- `applyTextTransform(text, transform)`: applies uppercase/lowercase/capitalize
- `buildFillStyle(ctx, style, ...)`: returns solid color or canvas gradient object
- Shadow rendering uses `ctx.shadowBlur` / `ctx.shadowColor` for blur support
- Stroke gated by `stroke_enabled`, shadow gated by `shadow_enabled`

### web/css/app.css — Component Styles
- `.style-group` / `.style-group-header` / `.style-group-body`: collapsible section styling
- `.style-label`, `.style-select`, `.style-range`, `.style-color`: form control styles

### core/exporter.py — Video Export Rendering
- `_get_word_style(word, seg_style, track)`: resolves effective style per word (style_override → group style → segment style)
- `_paint_subtitle()`: dispatcher — checks for special words and routes to word-by-word or uniform rendering
- `_paint_subtitle_word_by_word()`: renders each word individually with its own style (font, fill, stroke, shadow, gradient) USING SKIA
- `_paint_subtitle_uniform()`: renders entire segment as one text block USING SKIA
- Fully utilizes `skia-python` for native gradients (`GradientShader.MakeLinear`), native shadows (`ImageFilters.DropShadow`), and strokes.
- Solves text clipping natively by leveraging `skia.Font.measureText` properties like `metrics.fAscent` for bounds.

## Web Editor Enhancements
- **UI-Only Group Highlighting**: Special groups are assigned deterministic colors in the **Timeline** and **Segments** panel using `getGroupColor(groupId, alpha)`. This is for editor-side identification only and does not affect the final export or preview.

## Changelog
- 2026-04-05: Added deterministic UI-only group highlighting to Timeline and Segments section for easier word group identification.
- 2026-04-05: Skia-Python Rendering Engine replacement — migrated Pillow to Skia to fix Devanagari text bounds overlaps and ensure exactly mapped text sizes.
- 2026-04-04: Fixed export — added per-word rendering for special word styles, fixed text trimming
- 2025-04-02: Initial creation — full style engine implementation across all files
