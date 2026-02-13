
import os
from dataclasses import dataclass

@dataclass
class NexusConfig:
    # --- LLM Settings ---
    # Provider: 'ollama' or 'llamacpp'
    LLM_PROVIDER: str = "ollama" 
    
    # Ollama Specific
    OLLAMA_MODEL: str = "gpt-oss:20b-cloud"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    
    # Llama.cpp Specific
    # Path to GGUF file
    LLAMA_CPP_PATH: str = r"d:\Agent-S\models\your-model.gguf" 
    LLAMA_CPP_N_CTX: int = 4096
    LLAMA_CPP_N_GPU_LAYERS: int = -1 # -1 for all
    
    # --- Memory Settings ---
    MEMORY_DIR: str = ".nexus_memory"
    EMBEDDING_MODEL: str = "intfloat/e5-base-v2"
    SIMILARITY_THRESHOLD: float = 0.75
    
    # Context Retrieval
    MAX_CONTEXT_CHUNKS: int = 3
    
    # --- Shell Settings ---
    SHELL_TIMEOUT: int = 120
    SHELL_SHOW_UI: bool = False # Set to True for visible window

# Global Config Instance
config = NexusConfig()
