# S3 Agent - Production Implementation

A production-ready implementation of the S3 Agent for GUI automation with computer vision capabilities.

## Overview

S3 Agent is an intelligent automation system that can:
- **See** the screen using computer vision (CV) and OCR
- **Understand** UI elements using LLM vision models
- **Act** by generating precise mouse and keyboard commands
- **Execute** complex tasks through code or GUI interactions

## Architecture

```
s3_agent/
├── core/                    # Core LLM infrastructure
│   ├── engine.py           # LLM engines (OpenAI, Anthropic, Ollama, Gemini)
│   └── mllm.py            # Multimodal LLM agent wrapper
├── agents/                  # Agent implementations
│   ├── grounding.py       # ACI - Agent Computer Interface
│   ├── worker.py          # Main worker agent with reasoning
│   ├── code_agent.py      # Python/Bash code execution
│   └── agent_s.py         # Main orchestrator
├── vision/                  # Computer Vision (NEW)
│   └── detector.py        # Screen capture, element detection, analysis
├── memory/                  # Memory systems
│   └── procedural_memory.py  # System prompts
├── utils/                   # Utilities
│   └── common_utils.py    # Helper functions
└── bbon/                    # Behavior Narrator
    └── behavior_narrator.py
```

## Key Features

### 1. Multi-Provider LLM Support
- OpenAI (GPT-4, GPT-4V)
- Anthropic (Claude 3.x with thinking mode)
- Ollama (local models)
- Google Gemini

### 2. Visual Element Detection
- OCR-based text extraction
- OpenCV-based UI element detection
- Dynamic coordinate generation
- Screen change detection

### 3. Intelligent Action Generation
- Natural language to pyautogui code
- 14+ UI actions (click, type, scroll, drag, hotkey, etc.)
- Platform-specific code (Windows/Mac/Linux)
- Safe execution with failsafe

### 4. Code Execution Agent
- Python/Bash script execution
- 20-step budget with monitoring
- File modification capabilities
- Verification logic

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# For OCR support (optional but recommended)
pip install pytesseract
# Also install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki

# For OpenCV support (optional)
pip install opencv-python
```

## Configuration

Create a `.env` file:

```env
# OpenAI
OPENAI_API_KEY=your_key_here

# Anthropic
ANTHROPIC_API_KEY=your_key_here

# Ollama (local)
OLLAMA_BASE_URL=http://localhost:11434/v1

# Google Gemini
GEMINI_API_KEY=your_key_here
```

## Quick Start

```python
from s3_agent import AgentS3
from s3_agent.vision import VisualAnalyzer

# Initialize agent
agent = AgentS3(
    engine_params={
        "engine_type": "ollama",
        "model": "qwen3:0.6b"
    }
)

# Perform task with vision
visual_analyzer = VisualAnalyzer()

# Analyze screen
analysis = visual_analyzer.analyze_screen("Find and click the search button")

# Get coordinates
coords = visual_analyzer.find_element_for_action("search button", analysis)

if coords:
    print(f"Found element at: {coords}")
    # Execute action
    import pyautogui
    pyautogui.click(coords[0], coords[1])
```

## Directory Structure

```
D:\Agent-S\
├── s3_agent/               # Main package
├── tests/                  # Test suite
├── examples/               # Example scripts
├── docs/                   # Documentation
├── config/                 # Configuration
├── assets/                 # Assets (screenshots, etc.)
├── requirements.txt        # Dependencies
├── setup.py               # Package setup
└── README.md              # This file
```

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test
python tests/test_comprehensive.py

# Run examples
python examples/test_components.py
```

## Safety Features

- **Failsafe**: Move mouse to top-left corner to immediately stop
- **Confirmation**: Demo scripts ask for confirmation before executing
- **Screenshots**: Capture before/after for verification
- **Timeouts**: Automatic timeout for operations

## Production Ready Components

✅ Core LLM engines (multi-provider)
✅ MLLM Agent (message management)
✅ Grounding Agent (ACI with 14 actions)
✅ Procedural Memory (system prompts)
✅ Visual Element Detection (OCR + CV)
✅ Screen Capture & Analysis
✅ Code Agent (Python/Bash execution)
✅ Worker Agent (reasoning loop)
⏳ Behavior Narrator (visual explanation)
⏳ CLI Application

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

MIT License - See LICENSE file

## Acknowledgments

Based on the S3 Agent research implementation with enhancements for production use.
