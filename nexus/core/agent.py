import json
import time
import os
import asyncio
from typing import List, Dict, Any, Optional

# Config
from nexus.config import config

# Components
from nexus.memory.rag import SemanticMemory
from nexus.core.session import Session
from nexus.core.llm import create_provider
from nexus.tools.registry import ToolRegistry
from nexus.tools.shell import run_shell
from nexus.tools.browser import browser_action


class NexusAgent:
    """
    Nexus: A Semantic, Shell-Integrated Autonomous Agent
    with Browser Automation capabilities.
    """
    def __init__(self):
        # 1. Initialize Components
        print(f"[Nexus] Loading Semantic Memory ({config.EMBEDDING_MODEL})...")
        self.memory = SemanticMemory()
        
        print(f"[Nexus] Loading Tool Registry...")
        self.registry = ToolRegistry()
        self.registry.register(run_shell)
        self.registry.register(browser_action)
        
        print(f"[Nexus] Initializing LLM Provider ({config.LLM_PROVIDER})...")
        self.llm = create_provider()
            
        # 2. Initialize Session
        self.session = Session(self._get_system_prompt())
        
        # 3. Start LiveView if enabled
        self._live_view = None
        if config.BROWSER_LIVE_VIEW:
            self._start_live_view()

    def _start_live_view(self):
        """Start the LiveView visual rendering server."""
        try:
            from nexus.browser.browser_client import BrowserClient
            from nexus.browser.live_view import LiveViewServer
            
            client = BrowserClient(
                base_url=config.BROWSER_CONTROL_URL,
                auth_token=config.BROWSER_AUTH_TOKEN,
                profile=config.BROWSER_PROFILE,
            )
            self._live_view = LiveViewServer(client, port=config.BROWSER_LIVE_VIEW_PORT)
            self._live_view.start()
        except ImportError as e:
            print(f"[Nexus] LiveView not available (install flask): {e}")
        except Exception as e:
            print(f"[Nexus] LiveView failed to start: {e}")

    def _get_system_prompt(self) -> str:
        return f"""# ROLE: Nexus
Nexus is an advanced, shell-integrated autonomous agent with browser automation capabilities, designed for high-precision data management, system automation, and web interaction.

# DESCRIPTION
You operate within a Windows environment with direct access to:
1. The local filesystem via shell commands
2. Persistent semantic memory for long-term knowledge
3. A full web browser for navigating and interacting with websites

# TOOLS & CAPABILITIES

## 1. Shell Integration (`run_shell`)
Execute Windows CMD/PowerShell commands. Use for file manipulation, directory traversal, and system operations.

## 2. Browser Automation (`browser_action`)
Control a web browser to navigate websites, interact with page elements, and extract information.

**Browser Workflow:**
1. `browser_action(action='launch')` — Start Chrome (do this first)
2. `browser_action(action='navigate', url='https://...')` — Open a website
3. `browser_action(action='snapshot')` — See page structure with element refs (e1, e2, ...)
4. `browser_action(action='click', ref='e3')` — Click element by ref
5. `browser_action(action='type', ref='e5', text='hello')` — Type into element
6. `browser_action(action='press', key='Enter')` — Press a key
7. `browser_action(action='screenshot')` — Capture visual screenshot
8. `browser_action(action='tabs')` — List open tabs

**Important:** Always use 'snapshot' first to see available elements and their refs before clicking or typing.

## 3. Semantic Memory
You are provided with a `RELEVANT MEMORY` block containing past context. Trust this data for recurring tasks and entity relationships.

# USAGE & DOMAIN KNOWLEDGE
- **Data Repository**: Primary data is located in `{os.getcwd()}`.
- **System Info & Apps Info**: Use shell to gather system information.
- **Key Files**:
    - `Emails_Supplier.xlsx`: Official directory for Supplier Names, Emails, and Contact Persons.
    - `Products.xlsx`: Inventory data including PIP, EAN, and 'Current Lowest' pricing.
- **Supplier Mapping**: The 'Current Lowest' column in `Products.xlsx` contains short names. Cross-reference with `Emails_Supplier.xlsx` to resolve full supplier names.

# CRITICAL CONSTRAINTS
- **Naming Integrity**: Always use FULL supplier names from `Emails_Supplier.xlsx` when updating master files.
- **Path Persistence**: Reuse known file paths from memory.
- **Precision**: Match product names and pricing exactly from source files.
- **Safety**: Perform non-destructive operations unless explicitly instructed.
- **Browser Safety**: Do not submit forms or make purchases without explicit user confirmation.

# OPERATIONAL METHODOLOGY
1. **Identify**: Determine if the task requires data retrieval, file modification, system exploration, or web interaction.
2. **Context Retrieval**: Check `RELEVANT MEMORY` first. If missing, use shell or browser to locate information.
3. **Data Pipeline**: 
    - For contact info: Search `Products.xlsx` → Extract supplier short name → Map to full name in `Emails_Supplier.xlsx` → Retrieve Email.
4. **Execution**: Formulate the specific command, browser action, or response.
"""

    def chat(self, user_input: str) -> str:
        """
        Main interaction loop with RAG and Retry logic.
        """
        # 1. Retrieve Context (RAG)
        context_chunks = self.memory.retrieve(user_input, top_k=config.MAX_CONTEXT_CHUNKS)
        context_str = "\n\n".join([f"- {c['text']} (Source: {c['metadata'].get('source', 'unknown')})" for c in context_chunks])
        if not context_str: context_str = "No relevant past memories found."
        
        print(f"\n[Nexus] Retrieved Context:\n{context_str[:200]}...\n")

        # 2. Update Session
        self.session.add_message("user", user_input)
        
        # Prepare messages for LLM (including context)
        history = self.session.get_history()
        messages_with_context = [
            history[0],  # System Prompt
            {"role": "system", "content": f"RELEVANT MEMORY:\n{context_str}"}
        ] + history[1:]
        
        # 3. Generate & Loop (Think -> Act)
        final_response_content = ""
        
        for turn in range(5):
            try:
                # Call LLM
                response = self.llm.chat(messages_with_context, tools=self.registry.get_schemas())
                
                # Handle Response — normalize across providers
                if hasattr(response, 'choices'):
                    msg = response.choices[0].message
                    content = msg.content
                    tool_calls = msg.tool_calls
                else:
                    msg = response['choices'][0]['message']
                    content = msg['content']
                    tool_calls = msg.get('tool_calls')

                # Add Assistant Message to History
                assistant_msg = {"role": "assistant", "content": content}
                if tool_calls:
                     serialized_tcs = []
                     for tc in tool_calls:
                         if hasattr(tc, 'model_dump'): serialized_tcs.append(tc.model_dump())
                         elif hasattr(tc, 'dict'): serialized_tcs.append(tc.dict())
                         else: serialized_tcs.append(tc)
                     assistant_msg["tool_calls"] = serialized_tcs
                
                self.session.add_message(**assistant_msg)
                messages_with_context.append(assistant_msg)
                
                # Check for Tool Calls
                if tool_calls:
                    print(f"[Nexus] Tool Calls: {len(tool_calls)}")
                    for tc in tool_calls:
                        # Parse Tool Call
                        if hasattr(tc, 'function'):
                             func_name = tc.function.name
                             args_str = tc.function.arguments
                             tc_id = tc.id
                        else:
                             func_name = tc['function']['name']
                             args_str = tc['function']['arguments']
                             tc_id = tc.get('id')
                        
                        try:
                            args = json.loads(args_str)
                            print(f"[Nexus] Executing {func_name} with {args}...")
                            
                            # Execute
                            tool_func = self.registry.get_tool(func_name)
                            if tool_func:
                                result = tool_func(**args)
                            else:
                                result = f"Error: Tool {func_name} not found."
                                
                        except Exception as e:
                            result = f"Error executing tool: {e}"
                            
                        print(f"[Nexus] Result: {str(result)[:200]}...")
                        
                        # Add Tool Output
                        tool_msg = {
                            "role": "tool", 
                            "content": str(result),
                            "tool_call_id": tc_id,
                            "name": func_name
                        }
                        self.session.add_message(**tool_msg)
                        messages_with_context.append(tool_msg)
                        
                    # Loop back to LLM to process results
                    continue
                else:
                    # No tool calls, we are done
                    final_response_content = content
                    break
                    
            except Exception as e:
                print(f"[Nexus] Error in loop: {e}")
                import traceback
                traceback.print_exc()
                final_response_content = f"I encountered an error: {e}"
                break

        # 4. Memorize
        if self._is_worth_remembering(user_input, final_response_content):
            print("[Nexus] Saving interaction to memory.")
            self.memory.add_memory(f"User: {user_input}\nNexus: {final_response_content}")
            
        return final_response_content

    def _is_worth_remembering(self, user_input: str, response: str) -> bool:
        """Filter out trivial interactions AND errors."""
        if "I encountered an error" in response or "Error executing tool" in response:
            return False
            
        if not response: return False
        
        if len(user_input.strip()) < 5 and user_input.lower().strip() in ['hi', 'hello', 'ok', 'thanks', 'cool']: 
            return False
        
        # Skip trivial shell navigations
        if "dir" in user_input.lower() or "ls" in user_input.lower():
            return False

        return True


if __name__ == "__main__":
    agent = NexusAgent()
    while True:
        u = input("User: ")
        if u == "exit": break
        print(agent.chat(u))
