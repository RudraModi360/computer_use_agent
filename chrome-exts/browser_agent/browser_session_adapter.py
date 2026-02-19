
import logging
from typing import Any, Optional, Callable
from bubus import EventBus
from pydantic import BaseModel, PrivateAttr, Field

class CommandSender:
    """Mock for client.send"""
    def __init__(self, relay: "RelayCDPClient"):
        self.relay = relay

    def __getattr__(self, domain: str):
        return DomainSender(self.relay, domain)

class DomainSender:
    """Mock for client.send.Domain"""
    def __init__(self, relay: "RelayCDPClient", domain: str):
        self.relay = relay
        self.domain = domain

    def __getattr__(self, method: str):
        return Command(self.relay, self.domain, method)

class Command:
    """Mock for client.send.Domain.method"""
    def __init__(self, relay: "RelayCDPClient", domain: str, method: str):
        self.relay = relay
        self.command = f"{domain}.{method}"

    async def __call__(self, params: dict = None, **kwargs):
        # Ignore session_id or other kwargs, use relay's tab_id
        return await self.relay.send(self.command, params)

class RelayCDPClient:
    """Adapts BrowserTools to look like cdp-use Client with nested command structure."""
    def __init__(self, browser_tools, tab_id: int):
        self.browser_tools = browser_tools
        self.tab_id = tab_id
        self.send = CommandSender(self)

    async def send_command(self, method: str, params: dict = None):
        """Direct send method."""
        # BrowserTools._cdp is sync, but we wrap it in async for partial compatibility
        res = self.browser_tools._cdp(self.tab_id, method, params)
        if "error" in res:
             # Basic error handling
             raise Exception(f"CDP Error {method}: {res['error']}")
        return res.get("result", {})
        
    # Alias for internal use if needed
    send_raw = send_command
    
    # In my helper above, I used send(command) but the valid usage is client.send.Domain.method()
    # But wait, does client have a direct send() method too?
    # cdp-use might have send(method, params) ?
    # If so, CommandSender needs to be callable too?
    # Usually usage is client.send.Page.enable()
    
    # To support direct .send() if needed, we can make CommandSender callable?
    # But in the code provided: client.send.Page.getLayoutMetrics
    # So send is an object.
    
    async def send(self, *args, **kwargs):
         # This should never be called if .send is CommandSender property?
         # Wait, I assigned self.send = CommandSender(self).
         pass


# Fix helper to call send_command
class Command:
    def __init__(self, relay: "RelayCDPClient", domain: str, method: str):
        self.relay = relay
        self.command = f"{domain}.{method}"

    async def __call__(self, session_id=None, params: dict=None, **kwargs):
        # session_id is passed by service but we manage via tab_id in relay
        return await self.relay.send_command(self.command, params)

class CDPSession:
    """Mock for cdp_session object."""
    def __init__(self, client: RelayCDPClient, session_id: str):
        self.cdp_client = client
        self.session_id = session_id


class BrowserSession(BaseModel):
    """Adapter to make chrome-exts look like browser-use Session."""
    model_config = {"arbitrary_types_allowed": True}

    event_bus: EventBus = Field(default_factory=EventBus)
    agent_focus_target_id: Optional[str] = None
    logger: Any = Field(default=None)
    
    _browser_tools: Any = PrivateAttr()

    def __init__(self, browser_tools, **data):
        super().__init__(**data)
        self._browser_tools = browser_tools
        self.logger = logging.getLogger("BrowserSessionAdapter")
        self.logger.setLevel(logging.DEBUG)

    async def get_or_create_cdp_session(self, target_id: str, focus: bool = False) -> CDPSession:
        """Get a CDP session for a specific target (tab)."""
        if target_id is None:
            raise ValueError("target_id cannot be None")
        
        # In our case session_id effectively maps to target_id (tab_id)
        client = RelayCDPClient(self._browser_tools, int(target_id))
        return CDPSession(client, session_id=target_id)

    @property
    def cdp_client(self):
        """Root CDP client. Not fully supported in relay mode."""
        # Provide a default client for tab 0 or ???
        # Used by some watchdogs?
        return RelayCDPClient(self._browser_tools, 0)
