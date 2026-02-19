
import os

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Relay server URL
RELAY_BASE_URL = os.environ.get("RELAY_BASE_URL", "http://127.0.0.1:18792")

# Ollama model to use
# OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemini-3-flash-preview")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b-cloud")
OLLAMA_FALLBACK_MODEL = os.environ.get("OLLAMA_FALLBACK_MODEL", "qwen3-vl:2b")
# OLLAMA_MODEL = "llama3.2-vision" # Local vision model option

# Max conversation turns
MAX_ITERATIONS = 30
MAX_CONVERSATION_MESSAGES = 20

# Tool definitions for Ollama
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_all_tabs",
            "description": "Get a list of all open tabs with their IDs and titles.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_new_tab",
            "description": "Open a new tab with the given URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to open"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to_url",
            "description": "Navigate a specific tab to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                    "url": {"type": "string", "description": "The URL to navigate to"},
                },
                "required": ["tab_id", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_interactive_elements",
            "description": "Get a list of interactive elements (buttons, links, inputs) on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click an element on the page using its CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                    "selector": {"type": "string", "description": "The CSS selector of the element to click"},
                },
                "required": ["tab_id", "selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fill_input",
            "description": "Fill a text input field with value.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                    "selector": {"type": "string", "description": "The CSS selector of the input"},
                    "text": {"type": "string", "description": "The text to type"},
                },
                "required": ["tab_id", "selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_page",
            "description": "Scroll the page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                    "direction": {"type": "string", "enum": ["up", "down"], "description": "Direction to scroll"},
                    "amount": {"type": "integer", "description": "Details pixels to scroll (default 500)"},
                },
                "required": ["tab_id", "direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_visible_text",
            "description": "Get the visible text content of the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_info",
            "description": "Get the URL and Title of the current page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                },
                "required": ["tab_id"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot of the current page to see what's happening.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                },
                "required": ["tab_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "Call this when the user's task is completed or if you cannot complete it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "description": "Whether the task was successful"},
                    "summary": {"type": "string", "description": "A brief summary of what was done"},
                },
                "required": ["success", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_at_coordinates",
            "description": "Click on a specific (x, y) coordinate on the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab"},
                    "x": {"type": "integer", "description": "The x coordinate to click"},
                    "y": {"type": "integer", "description": "The y coordinate to click"},
                },
                "required": ["tab_id", "x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_tab",
            "description": "Switch to a specific tab by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_id": {"type": "integer", "description": "The ID of the tab to switch to"},
                },
                "required": ["tab_id"],
            },
        },
    }
]

