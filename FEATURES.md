# 🌟 OWN: Detailed Features Documentation

OWN (Only What's Needed) is a comprehensive, offline-first application for AI-powered video transcription, subtitle styling, and export. This document provides an in-depth look at all the features available in the application.

---

## 🎙️ 1. AI Transcription Engine

OWN utilizes state-of-the-art speech recognition to generate accurate subtitles locally.

### Whisper Integration
- **Local Processing**: Powered by `faster-whisper` (CTranslate2), ensuring fast inference on CPUs without requiring a GPU or internet connection.
- **Multiple Models**: 
  - `faster-whisper-large-v3-turbo`: The default model. Balances exceptional accuracy with faster processing speeds.
  - `faster-whisper-large-v3`: The largest model for maximum accuracy on complex audio.
- **Chunked Processing**: To handle long videos and manage RAM usage, audio is split into smaller chunks (default: 30 seconds) based on silence detection.
- **Silence Detection**: Uses `FFmpeg` to detect precise silence boundaries (`-40dB` threshold), ensuring that audio splits don't cut off words mid-sentence.
- **Word-Level Timestamps**: Every transcribed word receives exact start and end times, enabling advanced features like Karaoke animations.

### Language Support
- **15+ Supported Languages**: English, Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Odia, Assamese, Urdu, Nepali, Sanskrit, and Sindhi.
- **Auto-Detection**: Whisper can automatically identify the spoken language in the video if not explicitly set by the user.

---

## 🔤 2. Indic Transliteration

For creators targeting pan-Indian audiences or users who prefer reading native scripts in the Roman alphabet.

- **Indic to Roman**: Converts native scripts (like Devanagari, Bengali, Tamil) into readable Roman/English letters.
- **Dual Engine Architecture**:
  1. **Rule-Based Engine**: Uses the `indic-transliteration` library for fast, standard phonetic conversion (e.g., ITRANS format).
  2. **LLM-Powered Engine**: Supports optional integration with local Large Language Models (e.g., `Gemma 4 GGUF` via `llama-cpp-python`). This allows for context-aware transliteration that handles conversational nuances better than strict phonetic rules.

---

## 🎨 3. Advanced Subtitle Styling

The application features a rich, professional-grade styling engine that mimics broadcast-quality software. 

### Global & Segment-Level Control
Styles can be applied globally to all subtitles or overridden on a per-segment basis for emphasis.

### Typography
- **Fonts**: Over 100 bundled, high-quality open-source fonts.
- **Customization**: Controls for Font Size, Font Weight, Font Style (Italic/Normal), and Text Transform (Uppercase/Lowercase).

### Colors & Fills
- **Solid Fill**: Standard solid color hex picker.
- **Gradient Fill**: Linear and Radial gradients with dual color selection and configurable gradient angles.

### Outlines (Stroke) & Shadows
- **Stroke**: Toggleable outline with configurable color and width to separate text from complex backgrounds.
- **Drop Shadow**: Toggleable shadow with adjustable color, blur radius, and X/Y offset values for depth.

### Backgrounds
- **Word Background**: Toggleable rectangular background per-word with adjustable color, mimicking popular social media caption styles.

### Layout & Spacing
- **Letter & Word Spacing**: Fine-tune the typography kerning.
- **Line Height**: Adjust spacing between multi-line subtitles.
- **Opacity**: Global text opacity control.
- **Rotation**: Rotate the subtitle text blocks.

### Markers & Overrides
- Mark specific words as **Highlighted** or **Spotlighted**, applying distinct style presets to emphasize key points in the speech.

---

## ✨ 4. Dynamic Animations

Bring subtitles to life with motion design. Animations are handled via CSS transitions for smooth, high-framerate playback.

### Line Animations (Per-Segment)
- **Fade**: Subtitle gently fades in.
- **Slide Up / Down**: Subtitle enters the screen via a vertical slide.
- **Pop / Scale**: Subtitle scales up dynamically on entry.
- **Duration Control**: Configurable animation speed (e.g., 0.3s).

### Word Animations
- **Typewriter**: Words appear sequentially, mimicking a typing effect.
- **Karaoke**: Words are highlighted sequentially based on their exact timestamps.
  - *Karaoke Customization*: Configure the highlight color and an optional trailing background color.

---

## ✂️ 5. Timeline & Synchronization Editor

A fully interactive UI for precise timing adjustments.

- **Visual Waveform**: Displays the audio waveform alongside the video timeline.
- **Drag and Drop Adjustment**: Visually drag segment boundaries on the timeline to tweak start and end times.
- **Positioning**: Drag and drop the subtitle box directly on the video preview, or use precise normalized X/Y sliders.
- **Video Trimming**: Select a range on the timeline and trim the video; subtitles automatically adjust their timestamps to match the cut.
- **Segment Splitting/Merging**: Split a subtitle block exactly at the playhead if it's too long, or delete unwanted segments.
- **Sentence vs. Word Mode**: Toggle between editing full sentences block-by-block or adjusting words per line.

---

## 🎬 6. Video Export & Rendering Pipeline

OWN includes a robust, local rendering engine that guarantees pixel-perfect output.

- **Headless Playwright Rendering**: Instead of relying on complex FFmpeg text filters, the app uses a headless Chromium browser to render the exact CSS and HTML of the subtitles frame-by-frame. This guarantees that what you see in the editor is exactly what is exported.
- **FFmpeg Integration**: The browser frames are piped directly into FFmpeg to be multiplexed with the original video and audio streams.
- **Formats**: Export to popular formats like MP4 (H.264) and WebM.
- **SRT Export**: Download a standard `.srt` file containing the raw text and timestamps for use in other software like Premiere Pro or YouTube.

---

## 🖥️ 7. Desktop Integration & Offline Architecture

Designed from the ground up to respect user privacy and system resources.

- **100% Offline**: No API keys, no cloud processing, no data harvesting. All transcription and rendering happen on the local machine.
- **Model Sideloading**: Download AI models as ZIP files and upload them locally. Great for restricted networks or offline editing bays.
- **System Tray App**: The app runs unobtrusively in the Windows system tray (`pystray`), allowing users to close the main window without killing background export tasks.
- **Background Task Management**: Cancel ongoing transcription, rendering, or model downloads at any time without locking up the UI.
- **Bundled Executable**: Packaged with `Nuitka` into a standalone Windows installer. FFmpeg, Python, Playwright, and all dependencies are bundled inside—no technical setup required for end users.
