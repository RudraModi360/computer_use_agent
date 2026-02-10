"""
Configuration for Computer Use Agent
"""

# VLM Backend Configuration
VLM_CONFIG = {
    # Ollama settings
    "ollama": {
        "host": "http://localhost:11434",
        "model": "llava:7b",  # or "moondream", "bakllava", etc.
        "timeout": 60,
    },
    # llama.cpp settings
    "llamacpp": {
        "model_path": None,  # Set to your GGUF model path
        "clip_model_path": None,  # Set to mmproj GGUF for vision
        "n_ctx": 4096,
        "n_gpu_layers": -1,  # -1 for all layers on GPU
    }
}

# Detection settings
DETECTION_CONFIG = {
    "ocr_enabled": True,
    "max_ocr_workers": 4,
    "selective_ocr": True,  # Only OCR text-likely elements
    "max_ocr_elements": 15,
}

# Execution settings
EXECUTION_CONFIG = {
    "click_duration": 0.1,  # Mouse movement animation time
    "type_interval": 0.02,  # Delay between keystrokes
    "show_visual_feedback": True,
}

# Feedback settings
FEEDBACK_CONFIG = {
    "change_threshold": 0.01,  # Minimum change % to consider significant
    "wait_after_action": 0.5,  # Wait time before checking changes
}

# Agent settings
AGENT_CONFIG = {
    "max_steps": 10,
    "max_retries": 2,
    "output_dir": "agent_output",
}

# Latency targets (for monitoring)
LATENCY_TARGETS = {
    "screenshot": 0.05,     # 50ms
    "detection": 0.3,       # 300ms (with selective OCR)
    "annotation": 0.05,     # 50ms
    "vlm_inference": 2.0,   # 2000ms
    "execution": 0.2,       # 200ms
    "total_step": 3.0,      # 3000ms per step
}
