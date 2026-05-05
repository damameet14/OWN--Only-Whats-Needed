"""LLM-based transliteration module for Indic text using Gemma."""

import os
import json
from typing import List, Dict, Optional

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

_llm_cache = {}

# Language code to script/language name mapping for LLM prompts
LANGUAGE_MAP = {
    "hi": {"name": "Hindi", "script": "Devanagari"},
    "en": {"name": "English", "script": "Latin"},
    "bn": {"name": "Bengali", "script": "Bengali"},
    "ta": {"name": "Tamil", "script": "Tamil"},
    "te": {"name": "Telugu", "script": "Telugu"},
    "mr": {"name": "Marathi", "script": "Devanagari"},
    "gu": {"name": "Gujarati", "script": "Gujarati"},
    "kn": {"name": "Kannada", "script": "Kannada"},
    "ml": {"name": "Malayalam", "script": "Malayalam"},
    "pa": {"name": "Punjabi", "script": "Gurmukhi"},
    "or": {"name": "Odia", "script": "Odia"},
    "as": {"name": "Assamese", "script": "Bengali"},
    "sa": {"name": "Sanskrit", "script": "Devanagari"},
    "ne": {"name": "Nepali", "script": "Devanagari"},
    "sd": {"name": "Sindhi", "script": "Arabic/Devanagari"},
    "ur": {"name": "Urdu", "script": "Arabic"},
}


def get_llm(model_path: str):
    if model_path not in _llm_cache:
        if Llama is None:
            raise ImportError("llama-cpp-python is not installed")
        
        # Load the model, optimize for speed/cpu
        _llm_cache[model_path] = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_threads=os.cpu_count() or 4,
            verbose=False,
        )
    return _llm_cache[model_path]

def is_llm_available(model_dir: str, filename: str) -> Optional[str]:
    """Check if the LLM model exists and return its path."""
    if not os.path.exists(model_dir):
        return None
    model_path = os.path.join(model_dir, filename)
    if os.path.exists(model_path) and Llama is not None:
        return model_path
    return None

def transliterate_indic_to_roman_llm(
    model_path: str,
    words: List[Dict],
    language: str = "hi",
) -> List[Dict]:
    """
    Transliterate an array of word objects containing Indic text
    into Romanized text using Gemma.

    Args:
        model_path: Path to the GGUF model file.
        words: List of dicts with 'word' and optionally 'index' keys.
        language: ISO 639-1 language code (e.g. 'hi', 'bn', 'ta').
    """
    if not words:
        return []

    try:
        llm = get_llm(model_path)
    except Exception as e:
        print(f"Failed to load LLM: {e}")
        return []

    # Resolve language info for the prompt
    lang_info = LANGUAGE_MAP.get(language, LANGUAGE_MAP["hi"])
    lang_name = lang_info["name"]
    script_name = lang_info["script"]

    results = []
    chunk_size = 50
    import re

    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i+chunk_size]
        input_texts = [w.get("word", "") for w in chunk_words]
        
        prompt = f"""You are a strict transliteration assistant. 
Transliterate the following {lang_name} words (written in {script_name} script) into Romanized text (ITRANS/ISO 15919).
Output ONLY a strict JSON array of strings in the exact same order and length as the input. Do not output any markdown formatting or extra text.

Input words: {json.dumps(input_texts, ensure_ascii=False)}
Output JSON array:"""

        try:
            response = llm(
                prompt,
                max_tokens=10240,
                temperature=0.1,
            )
            
            output_text = response['choices'][0]['text'].strip()
            
            # Try to extract JSON array using regex if there's extra text
            match = re.search(r'\[.*\]', output_text, re.DOTALL)
            if match:
                output_text = match.group(0)
                
            try:
                transliterated_list = json.loads(output_text.strip())
            except Exception as e:
                print(f"JSON Parse Error: {e}, falling back to manual extraction")
                clean_text = output_text.strip()
                if clean_text.startswith('['): clean_text = clean_text[1:]
                if clean_text.endswith(']'): clean_text = clean_text[:-1]
                transliterated_list = [item.strip(' \n\r\t"\'') for item in clean_text.split(',')]
            
            for j, original_w in enumerate(chunk_words):
                if j < len(transliterated_list) and transliterated_list[j]:
                    results.append({
                        "index": original_w.get("index", i + j),
                        "original": original_w.get("word", ""),
                        "roman": transliterated_list[j],
                    })
                else:
                    # fallback
                    results.append({
                        "index": original_w.get("index", i + j),
                        "original": original_w.get("word", ""),
                        "roman": original_w.get("word", ""),
                    })

        except Exception as e:
            print(f"LLM transliteration failed for chunk: {e}")
            for j, original_w in enumerate(chunk_words):
                results.append({
                    "index": original_w.get("index", i + j),
                    "original": original_w.get("word", ""),
                    "roman": original_w.get("word", ""),
                })

    return results
