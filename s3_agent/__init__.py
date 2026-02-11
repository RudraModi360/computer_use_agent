"""
S3 Agent package initialization.
"""

__version__ = '0.1.0'

# Core imports - will be available when modules are imported directly
# from .core.mllm import LMMAgent
# from .core.engine import LMMEngine
# from .agents.grounding import OSWorldACI
# from .agents.worker import Worker
# from .agents.agent_s import AgentS3
# from .vision.detector import VisualAnalyzer, ScreenshotManager

__all__ = [
    # Core
    'core',
    # Agents
    'agents',
    # Vision
    'vision',
    # Memory
    'memory',
    # Utils
    'utils',
]
