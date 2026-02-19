const DEFAULT_PORT = 18792;

// Badge configurations
const BADGE = {
  on: { text: 'ON', color: '#10B981' },
  off: { text: '', color: '#000000' },
  connecting: { text: '...', color: '#F59E0B' },
  error: { text: '!', color: '#EF4444' },
  collecting: { text: '▼', color: '#3B82F6' }
};

// State management
let relayWs = null;
let relayConnectPromise = null;
let nextRequestId = 1;
const pendingRequests = new Map();
const attachedTabs = new Map(); // tabId -> {sessionId, targetId}

// Initialize on install
chrome.runtime.onInstalled.addListener(async () => {
  console.log('[Chrome Tracker] Extension installed');
  chrome.storage.local.set({ relayPort: DEFAULT_PORT });
  // Set up periodic alarm to keep service worker alive and auto-reconnect
  chrome.alarms.create('relay-keepalive', { periodInMinutes: 0.15 }); // ~10 seconds
  // Try connecting and collecting immediately
  try {
    await ensureRelayConnection();
    await collectAllTabs();
  } catch (e) { }
});

// On Chrome startup, try to connect and collect immediately
chrome.runtime.onStartup.addListener(async () => {
  console.log('[Chrome Tracker] Chrome started, connecting to relay...');
  chrome.alarms.create('relay-keepalive', { periodInMinutes: 0.15 });
  try {
    await ensureRelayConnection();
    await collectAllTabs();
  } catch (e) { }
});

// Periodic alarm: wake up, ensure connected, collect tabs on reconnect only
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'relay-keepalive') {
    if (!relayWs || relayWs.readyState !== WebSocket.OPEN) {
      console.log('[Chrome Tracker] Alarm: not connected, trying to reconnect...');
      try {
        await ensureRelayConnection();
        console.log('[Chrome Tracker] Alarm: reconnected — collecting tabs...');
        await collectAllTabs();
      } catch (err) {
        // Relay not up yet, will try again on next alarm
      }
    }
    // When already connected, do nothing — tabs are collected on connect and on-demand
  }
});

// Handle extension icon click
chrome.action.onClicked.addListener(async () => {
  console.log('[Chrome Tracker] Icon clicked - collecting all tabs');
  await collectAllTabs();
});

// Listen for messages from Python relay
function setBadge(kind) {
  const cfg = BADGE[kind];
  chrome.action.setBadgeText({ text: cfg.text });
  chrome.action.setBadgeBackgroundColor({ color: cfg.color });
}

async function getRelayPort() {
  const stored = await chrome.storage.local.get(['relayPort']);
  const port = parseInt(stored.relayPort || DEFAULT_PORT, 10);
  return (port > 0 && port <= 65535) ? port : DEFAULT_PORT;
}

async function ensureRelayConnection() {
  if (relayWs?.readyState === WebSocket.OPEN) return;
  if (relayConnectPromise) return await relayConnectPromise;

  relayConnectPromise = (async () => {
    const port = await getRelayPort();
    const wsUrl = `ws://127.0.0.1:${port}/extension`;

    console.log(`[Chrome Tracker] Connecting to relay at ${wsUrl}`);

    // Preflight check
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, {
        signal: AbortSignal.timeout(2000)
      });
      if (!response.ok) throw new Error('Health check failed');
    } catch (err) {
      throw new Error(`Relay server not reachable at port ${port}`);
    }

    const ws = new WebSocket(wsUrl);
    relayWs = ws;

    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('WebSocket connection timeout'));
      }, 5000);

      ws.onopen = () => {
        clearTimeout(timeout);
        console.log('[Chrome Tracker] Connected to relay');
        setBadge('on');
        resolve();
      };

      ws.onerror = (err) => {
        clearTimeout(timeout);
        reject(new Error('WebSocket connection failed'));
      };

      ws.onclose = () => {
        clearTimeout(timeout);
        reject(new Error('WebSocket closed unexpectedly'));
      };
    });

    ws.onmessage = (event) => handleRelayMessage(event.data);
    ws.onclose = () => handleRelayClose();
    ws.onerror = (err) => console.error('[Chrome Tracker] WebSocket error:', err);

  })();

  try {
    await relayConnectPromise;
  } finally {
    relayConnectPromise = null;
  }
}

function handleRelayClose() {
  console.log('[Chrome Tracker] Relay disconnected');
  relayWs = null;
  relayConnectPromise = null;
  setBadge('off');

  // Reject all pending requests
  for (const [id, { reject }] of pendingRequests) {
    try { reject(new Error('Relay disconnected')); } catch (e) { }
  }
  pendingRequests.clear();

  // Auto-reconnect after 1 second, alarm will also retry every ~10s
  setTimeout(async () => {
    console.log('[Chrome Tracker] Attempting auto-reconnect...');
    try {
      await ensureRelayConnection();
      console.log('[Chrome Tracker] Auto-reconnected successfully');
      // Re-collect tabs after reconnect
      await collectAllTabs();
    } catch (err) {
      console.log('[Chrome Tracker] Auto-reconnect failed, alarm will retry in ~10s');
      // No need for recursive setTimeout - the alarm handles periodic retries
    }
  }, 1000);
}

async function handleRelayMessage(data) {
  try {
    const msg = JSON.parse(data);

    if (msg.method === 'ping') {
      relayWs.send(JSON.stringify({ method: 'pong' }));
      return;
    }

    if (msg.id !== undefined && pendingRequests.has(msg.id)) {
      const { resolve, reject } = pendingRequests.get(msg.id);
      pendingRequests.delete(msg.id);

      if (msg.error) {
        reject(new Error(msg.error));
      } else {
        resolve(msg.result);
      }
      return;
    }

    if (msg.method === 'executeCDP') {
      // Execute CDP command and return result
      try {
        const result = await executeCDPCommand(msg.params);
        sendToRelay({ id: msg.id, result });
      } catch (cdpErr) {
        console.error('[Chrome Tracker] CDP execution error:', cdpErr);
        sendToRelay({ id: msg.id, result: { success: false, error: cdpErr.message } });
      }
    }

    if (msg.method === 'activateTab') {
      // Bring Chrome window to foreground and switch to the target tab
      try {
        const tabId = msg.params?.tabId;
        if (tabId) {
          const tab = await chrome.tabs.get(tabId);
          await chrome.tabs.update(tabId, { active: true });
          await chrome.windows.update(tab.windowId, { focused: true });
          sendToRelay({ id: msg.id, result: { success: true } });
        } else {
          sendToRelay({ id: msg.id, result: { success: false, error: 'No tabId provided' } });
        }
      } catch (err) {
        console.error('[Chrome Tracker] activateTab error:', err);
        sendToRelay({ id: msg.id, result: { success: false, error: err.message } });
      }
    }

    if (msg.method === 'openNewTab') {
      // Open a new tab and bring it to front
      try {
        const url = msg.params?.url || 'https://www.google.com';
        const tab = await chrome.tabs.create({ url, active: true });
        await chrome.windows.update(tab.windowId, { focused: true });
        sendToRelay({ id: msg.id, result: { success: true, tabId: tab.id } });
      } catch (err) {
        console.error('[Chrome Tracker] openNewTab error:', err);
        sendToRelay({ id: msg.id, result: { success: false, error: err.message } });
      }
    }
  } catch (err) {
    console.error('[Chrome Tracker] Error handling message:', err);
  }
}

function sendToRelay(payload) {
  if (relayWs?.readyState === WebSocket.OPEN) {
    relayWs.send(JSON.stringify(payload));
  } else {
    throw new Error('Relay not connected');
  }
}

async function sendRequest(method, params = {}) {
  const id = nextRequestId++;

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      pendingRequests.delete(id);
      console.warn(`[Chrome Tracker] Request timeout: ${method} (id=${id})`);
      // Resolve with error instead of rejecting to prevent uncaught promise crashes
      resolve({ error: `Request timeout: ${method}`, timed_out: true });
    }, 10000);  // 10s timeout (was 30s)

    pendingRequests.set(id, {
      resolve: (result) => {
        clearTimeout(timeout);
        resolve(result);
      },
      reject: (err) => {
        clearTimeout(timeout);
        // Resolve with error object instead of rejecting
        console.warn(`[Chrome Tracker] Request error for ${method}:`, err.message);
        resolve({ error: err.message });
      }
    });

    try {
      sendToRelay({ id, method, params });
    } catch (err) {
      pendingRequests.delete(id);
      clearTimeout(timeout);
      console.warn(`[Chrome Tracker] Failed to send ${method}:`, err.message);
      resolve({ error: err.message });
    }
  });
}

// Main function: Collect all tabs
async function collectAllTabs() {
  setBadge('collecting');

  try {
    await ensureRelayConnection();

    console.log('[Chrome Tracker] Starting tab collection');

    // Method 1: Quick scan - get all tabs metadata
    const allTabs = await chrome.tabs.query({});
    console.log(`[Chrome Tracker] Found ${allTabs.length} tabs`);

    // Send quick data immediately (fire-and-forget — relay stores but doesn't ACK)
    const quickData = allTabs.map(tab => ({
      id: tab.id,
      url: tab.url,
      title: tab.title,
      windowId: tab.windowId,
      active: tab.active,
      pinned: tab.pinned,
      groupId: tab.groupId,
      favIconUrl: tab.favIconUrl,
      timestamp: Date.now()
    }));

    sendToRelay({ method: 'tabDataQuick', params: { tabs: quickData } });
    console.log('[Chrome Tracker] Quick data sent');

    // Method 2: Deep scan - get DOM content from active tab only
    const activeTab = allTabs.find(t => t.active);
    if (activeTab && activeTab.url && !activeTab.url.startsWith('chrome://')) {
      try {
        const domData = await getTabDOM(activeTab.id, activeTab);
        sendToRelay({ method: 'tabDataDeep', params: { tab: domData } });
        console.log('[Chrome Tracker] Deep data sent for active tab');
      } catch (err) {
        console.error('[Chrome Tracker] Failed to get DOM:', err.message);
      }
    }

    // Signal collection complete (fire-and-forget)
    sendToRelay({
      method: 'collectionComplete', params: {
        totalTabs: allTabs.length,
        timestamp: Date.now()
      }
    });

    setBadge('on');

  } catch (err) {
    console.error('[Chrome Tracker] Collection failed:', err);
    setBadge('error');
    throw err;
  }
}

// Get DOM content via CDP
async function getTabDOM(tabId, tabInfo) {
  // Skip chrome:// URLs — cannot access them
  if (tabInfo?.url?.startsWith('chrome://') || tabInfo?.url?.startsWith('chrome-extension://')) {
    throw new Error('Cannot access chrome:// URL');
  }

  try {
    // Attach debugger
    await chrome.debugger.attach({ tabId }, '1.3');

    // Enable necessary domains
    await chrome.debugger.sendCommand({ tabId }, 'Runtime.enable');
    await chrome.debugger.sendCommand({ tabId }, 'Page.enable');

    // Get full HTML
    const htmlResult = await chrome.debugger.sendCommand(
      { tabId },
      'Runtime.evaluate',
      { expression: 'document.documentElement.outerHTML' }
    );

    // Get page metrics
    const metrics = await chrome.debugger.sendCommand(
      { tabId },
      'Page.getLayoutMetrics'
    );

    // Get title and URL from page
    const titleResult = await chrome.debugger.sendCommand(
      { tabId },
      'Runtime.evaluate',
      { expression: 'document.title' }
    );

    // Detach debugger
    await chrome.debugger.detach({ tabId });

    return {
      id: tabId,
      url: tabInfo.url,
      title: titleResult?.result?.value || tabInfo.title,
      html: htmlResult?.result?.value || '',
      layoutMetrics: metrics,
      timestamp: Date.now()
    };

  } catch (err) {
    console.error(`[Chrome Tracker] Failed to get DOM for tab ${tabId}:`, err);
    // Ensure detach even on error
    try { await chrome.debugger.detach({ tabId }); } catch { }
    throw err;
  }
}

// Execute CDP command (called from Python)
async function executeCDPCommand({ tabId, method, params = {} }) {
  try {
    // Verify the tab still exists
    try {
      await chrome.tabs.get(tabId);
    } catch (e) {
      return { success: false, error: `Tab ${tabId} not found or is closed` };
    }

    // Attach if not already attached (or re-attach if stale)
    if (!attachedTabs.has(tabId)) {
      try {
        await chrome.debugger.attach({ tabId }, '1.3');
      } catch (attachErr) {
        // Already attached? That's fine, just record it
        if (!attachErr.message?.includes('Already attached')) {
          return { success: false, error: `Failed to attach debugger: ${attachErr.message}` };
        }
      }
      attachedTabs.set(tabId, {
        sessionId: `tab-${tabId}-${Date.now()}`,
        targetId: null
      });
    }

    const result = await chrome.debugger.sendCommand({ tabId }, method, params);
    return { success: true, result };
  } catch (err) {
    // If debugger detached, try re-attaching once
    if (err.message?.includes('Debugger is not attached') || err.message?.includes('not attached')) {
      attachedTabs.delete(tabId);
      try {
        await chrome.debugger.attach({ tabId }, '1.3');
        attachedTabs.set(tabId, {
          sessionId: `tab-${tabId}-${Date.now()}`,
          targetId: null
        });
        const result = await chrome.debugger.sendCommand({ tabId }, method, params);
        return { success: true, result };
      } catch (retryErr) {
        return { success: false, error: `Retry failed: ${retryErr.message}` };
      }
    }
    return { success: false, error: err.message };
  }
}

// Listen for CDP events
chrome.debugger.onEvent.addListener((source, method, params) => {
  // Forward events to relay
  if (relayWs?.readyState === WebSocket.OPEN) {
    sendToRelay({
      method: 'cdpEvent',
      params: { source, method, params }
    });
  }
});

chrome.debugger.onDetach.addListener((source, reason) => {
  attachedTabs.delete(source.tabId);
  console.log(`[Chrome Tracker] Detached from tab ${source.tabId}: ${reason}`);
});

// Handle tab changes
chrome.tabs.onCreated.addListener((tab) => {
  if (relayWs?.readyState === WebSocket.OPEN) {
    sendToRelay({
      method: 'tabEvent',
      params: { type: 'created', tab: { id: tab.id, url: tab.url, title: tab.title } }
    });
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (relayWs?.readyState === WebSocket.OPEN && (changeInfo.url || changeInfo.title)) {
    sendToRelay({
      method: 'tabEvent',
      params: {
        type: 'updated',
        tabId,
        changes: changeInfo,
        tab: { id: tab.id, url: tab.url, title: tab.title }
      }
    });
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  attachedTabs.delete(tabId);
  if (relayWs?.readyState === WebSocket.OPEN) {
    sendToRelay({
      method: 'tabEvent',
      params: { type: 'removed', tabId }
    });
  }
});

console.log('[Chrome Tracker] Background script loaded');