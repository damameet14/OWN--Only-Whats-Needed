# OWN (Only What's Needed) - User Guide

Welcome to **OWN**! This guide will help you understand all the features of the application and how to use them to auto-caption your videos easily and completely offline.

> **Note:** Some screen names and screens within the app are currently placeholders and will be fully implemented in later versions.

## 🌟 Features Overview

### 1. AI Video Transcription
* **Completely Offline:** We use advanced AI models (like Whisper) that run completely offline on your computer. No internet is required to transcribe!
* **Word-Level Timestamps:** Every single word is tracked with its exact start and end time, allowing for precise editing and animations.
* **Handles Long Videos:** The app automatically splits audio into manageable chunks to ensure your computer doesn't run out of memory during processing.

### 2. Multi-Language Support
You can transcribe videos spoken in various languages, including over 15 Indian languages (Hindi, Bengali, Tamil, Telugu, Marathi, etc.).

**How to use Multi-Language Transcription:**
* During video upload, select the **Whisper Large v3** model (do not use the Turbo model for the best multi-language accuracy).
* In the Language dropdown, select **🌐 Auto Detect**.
* *Tip:* If the Auto Detect option does not give you the desired output, manually select the specific Indian language you have spoken from the dropdown list.
* **Important Note:** Processing can take time depending on your computer's speed. A video of over 1 minute can take up to 8-10 minutes for transcription with the large model, so please be patient!

### 3. Indic Transliteration
Convert subtitles from native Indian scripts (like Devanagari, Bengali, Tamil, etc.) into readable English/Roman letters. Great for audiences who prefer reading native languages in the English alphabet.

**How to use Transliteration:**
* Use the Transliteration option in the editor after your native-script subtitles are generated.
* *Note:* Sometimes the transliteration process might not work properly on the first try. If that happens, simply **close the app and try again**.

### 4. Advanced Subtitle Styling
Make your captions pop with broadcast-quality styling!
* **Typography:** Choose from over 100 bundled high-quality fonts. Adjust font size, weight (boldness), italics, and uppercase/lowercase styling. You can also upload your own font!
* **Colors & Gradients:** Use solid colors or create beautiful linear and radial gradients with dual colors.
* **Outlines & Shadows:** Add strokes (outlines) and drop shadows to separate text from complex video backgrounds.
* **Word Backgrounds:** Toggle a rectangular background behind each word, mimicking popular social media caption styles.
* **Layout & Spacing:** Fine-tune letter spacing, line height, overall opacity, and even rotate the text.
* **Highlights:** Mark specific words as "Highlighted" or "Spotlighted" to emphasize key points in your speech.

### 5. Dynamic Animations
Bring your subtitles to life with smooth motion design.
* **Line Animations:** Choose how subtitle blocks enter the screen (Fade, Slide Up/Down, Pop/Scale) and control the animation duration.
* **Word Animations:** Use the **Typewriter** effect (words appear one by one) or the **Karaoke** effect (words are highlighted sequentially exactly when spoken). You can even customize the Karaoke highlight colors.

### 6. Timeline & Synchronization Editor
Manually fix any misheard words or adjust the exact timing of the captions on the screen using the interactive editor.
* **Visual Waveform:** See the audio waveform alongside your video for precise timing adjustments.
* **Drag and Drop Timing:** Drag the edges of the blocks on the bottom timeline to adjust exactly when a subtitle appears or disappears.
* **Repositioning:** Drag the subtitle box directly on the video player preview to move it, or use the exact X/Y sliders.
* **Video Trimming:** Select a portion of the timeline to trim your video; subtitles will automatically adjust to the cut. *(Note: Not fully functional in this version)*
* **Split & Merge:** Break long subtitles into shorter ones exactly where you want them, or delete unwanted segments. *(Note: Not fully functional in this version)*
* **Sentence vs. Word Mode:** Toggle between editing full sentences block-by-block or adjusting individual words.

### 7. Desktop App & Background Tasks
* **System Tray integration:** The app runs smoothly in your Windows system tray. You can close the main window and your video exports will safely continue running in the background.
* **Task Management:** Cancel ongoing transcriptions, renders, or model downloads at any time without locking up your computer.

### 8. Video Export & SRT Download
* **Video Export:** Once you are happy with the preview, click "Export Video". Your video will be rendered locally to MP4 or WebM with the subtitles hardcoded perfectly.
* **SRT Download:** Need the subtitles for YouTube or Premiere Pro? Just download the standard `.srt` file containing the raw text and timestamps.

---

## 📥 Downloading AI Models

To use the app, you need to download the AI models. You can either download them directly inside the app, or manually download the ZIP files if you prefer.

**Manual ZIP Download Links:**
* [Whisper Large v3 Model (Recommended for Multi-Language)](https://drive.google.com/uc?export=download&id=1HF7WJodZDrVzTq0PHdgtT9G2pAprvLhL) - ~3 GB
* [Whisper Large v3 Turbo Model (Faster, default for English)](https://drive.google.com/uc?export=download&id=1dIcOkDQmQ6ga_VhUNHqm3_Fb28PveHQZ) - ~800 MB
* [Gemma Transliteration Model (Required for LLM Transliteration)](https://drive.google.com/uc?export=download&id=1yuV1vUeyvcA1AVEeJjwoECIRMsPcGyTx) - ~1.5 GB

**How to install manually:**
1. Download the ZIP file from the links above.
2. In the app, choose the option to upload or install a local model.
3. Select the downloaded ZIP file and wait for it to install.
