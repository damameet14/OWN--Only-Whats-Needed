"""LLM-based transliteration module for Indic text using Gemma."""

import os
import json
from typing import List, Dict, Optional

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

_llm_cache = {}

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

def transliterate_indic_to_roman_llm(model_path: str, words: List[Dict]) -> List[Dict]:
    """
    Transliterate an array of word objects containing Indic text
    into Romanized text using Gemma.
    """
    if not words:
        return []

    try:
        llm = get_llm(model_path)
    except Exception as e:
        print(f"Failed to load LLM: {e}")
        return []

    input_texts = [w.get("word", "") for w in words]
    
    prompt = f"""You are a strict transliteration assistant. 
Transliterate the following Hindi words into Romanized Hindi (ITRANS).
Output ONLY a strict JSON array of strings in the exact same order and length as the input. Do not output any markdown formatting or extra text.

Input words: {json.dumps(input_texts, ensure_ascii=False)}
Output JSON array:"""

    try:
        response = llm(
            prompt,
            max_tokens=1024,
            stop=["\n\n", "```"],
            temperature=0.1,
        )
        
        output_text = response['choices'][0]['text'].strip()
        
        if output_text.startswith("```json"):
            output_text = output_text[7:]
        if output_text.startswith("```"):
            output_text = output_text[3:]
        if output_text.endswith("```"):
            output_text = output_text[:-3]
            
        transliterated_list = json.loads(output_text.strip())
        
        results = []
        for i, original_w in enumerate(words):
            if i < len(transliterated_list):
                results.append({
                    "index": original_w.get("index", i),
                    "original": original_w.get("word", ""),
                    "roman": transliterated_list[i],
                })
            else:
                # fallback
                results.append({
                    "index": original_w.get("index", i),
                    "original": original_w.get("word", ""),
                    "roman": original_w.get("word", ""),
                })
        return results

    except Exception as e:
        print(f"LLM transliteration failed: {e}")
        return []
