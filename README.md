# Nexus Agent - Modular

Nexus is a lightweight, semantic-memory-augmented autonomous agent with native shell access for Windows.

## Directory Structure

```
nexus/
  ├── config.py           # Configuration (Models, Paths)
  ├── core/               # Main Agent Logic
  ├── memory/             # Semantic RAG Implementation
  ├── tools/              # Tool Definitions
  └── utils/              # Backend Services (Shell Manager)
```

## Key Features

1.  **Persistent Semantic Memory**: 
    - Uses `intfloat/e5-base-v2` for high-quality local embeddings.
    - Implements **Semantic Chunking**.
    - Stores interactions in a local vector store (`.nexus_memory/`).

2.  **Native Shell Interface**:
    - Spawns a visible, persistent **Shell Satellite** window.
    - Commands run in real-time in the user's view.

3.  **Multi-Provider Support**:
    - Supports **Ollama** (default) and **Llama.cpp**.
    - Configure in `nexus/config.py`.

## Usage

1.  **Install Dependencies**:
    ```bash
    pip install openai sentence-transformers faiss-cpu numpy
    # Optional for local GGUF
    pip install llama-cpp-python 
    ```

2.  **Run Agent**:
    ```bash
    python run_nexus.py
    ```

3.  **Interact**:
    - "List files in current directory" -> Runs `dir`.
    - "Remember that the project code is 42" -> Saves to semantic memory.

## Configuration
Edit `nexus/config.py`:
```python
@dataclass
class NexusConfig:
    LLM_PROVIDER: str = "ollama" # or "llamacpp"
    ...
```
