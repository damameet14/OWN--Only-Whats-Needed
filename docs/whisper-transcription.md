# Whisper Transcription Guide

## Overview

OWN supports two transcription engines:

1. **Vosk** - Lightweight, Hindi-focused models
2. **Whisper** - Multilingual, higher accuracy, requires more RAM

## Whisper Models

### Large v3 Turbo (Recommended)
- Size: ~800 MB
- RAM: ~4 GB recommended
- Accuracy: High
- Speed: Fast

### Large v3
- Size: ~3 GB
- RAM: ~8 GB recommended
- Accuracy: Very High
- Speed: Slower

## How to Use

1. Open a project in the editor
2. Click "Transcribe" button
3. Select "Whisper (Multilingual)" as the engine
4. Choose your preferred model
5. If not installed, click "Download Model"
6. Click "Start Transcription"

## Chunked Processing

Whisper transcription uses chunked processing to manage RAM usage:
- Audio is split into ~30-second chunks at silence boundaries
- Each chunk is processed sequentially
- Word timings are automatically adjusted across chunks
- Progress is shown in real-time

## Troubleshooting

### Out of Memory
If you encounter out-of-memory errors:
- Use the "Large v3 Turbo" model instead of "Large v3"
- Close other applications to free up RAM
- Ensure you have at least 4 GB RAM available

### Slow Transcription
Transcription speed depends on:
- CPU performance (Whisper is CPU-intensive)
- Model size (Turbo is faster than Large v3)
- Video length

### Poor Accuracy
For better accuracy:
- Ensure clear audio quality
- Use the "Large v3" model (slower but more accurate)
- Check that the correct language is selected
