export function initAIGenerator() {
  console.log("🚀 AI Generator Initializing...");
  
  const generateBtn = document.getElementById('generate-ai');
  const panel = document.getElementById('ai-generator-panel');
  const userInput = document.getElementById('user-input');
  const chatMessages = document.getElementById('chat-messages');
  const chatLimitStatus = document.getElementById('chat-limit-status');
  const backendStatusBadge = document.getElementById('backend-status-badge');
  const reconnectBtn = document.getElementById('reconnect-btn');

  console.log("Elements found:", {
    generateBtn: !!generateBtn,
    userInput: !!userInput,
    chatMessages: !!chatMessages
  });

  if (!generateBtn || !panel || !userInput || !chatMessages) {
    console.error("❌ Missing essential AI generator elements");
    return;
  }

  let chatHistory = [];
  let isLoading = false;
  let cooldownUntil = 0;
  let messageTimestamps = [];
  let statusTimerId = null;
  let activeExplosionOverlay = null;
  let explosionCleanupTimeoutId = null;
  let backendStatus = 'unknown';
  const COOLDOWN_MS = 3000;
  const LIMIT_WINDOW_MS = 30 * 1000;
  const MAX_MESSAGES_PER_WINDOW = 3;
  let hasTriggeredLimitEgg = false;
  let isExplosionActive = false;
  
  // Multiple server fallbacks
  const servers = [
    'https://yappotamus.onrender.com'
  ];
  
  let currentServer = servers[0];

  // Ensure panel is always visible
  panel.style.display = 'block';
  updateLimitStatus();
  startStatusTimer();
  setBackendStatus('unknown');

  if (reconnectBtn) {
    reconnectBtn.addEventListener('click', () => {
      void pingBackend();
    });
  }

  generateBtn.addEventListener('click', () => {
    console.log("🎯 Generate button clicked!");
    handleGenerate();
  });
  
  userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      console.log("⌨️ Enter key pressed!");
      handleGenerate();
    }
  });

  async function handleGenerate() {
    const message = userInput.value.trim();
    console.log("💬 Handling generate with message:", message);
    
    if (!message) {
      alert("Please enter a message.");
      return;
    }

    if (isLoading) {
      console.log("⏳ Already loading, ignoring click");
      return;
    }

    const now = Date.now();
    pruneMessageTimestamps(now);

    if (message.toLowerCase() === 'yapvibes' && messageTimestamps.length >= MAX_MESSAGES_PER_WINDOW) {
      triggerFullscreenExplosion('fire');
      addMessage('💥 BOOM! Secret code accepted: yapvibes', 'ai', 'yapBot Secret');
      userInput.value = '';
      return;
    }

    if (message.toLowerCase() === 'supernova' && messageTimestamps.length >= MAX_MESSAGES_PER_WINDOW) {
      triggerFullscreenExplosion('nova');
      addMessage('🌌 SUPERNOVA MODE ACTIVATED! Secret code accepted: supernova', 'ai', 'yapBot Secret');
      userInput.value = '';
      return;
    }

    if (messageTimestamps.length >= MAX_MESSAGES_PER_WINDOW) {
      const resetInMs = LIMIT_WINDOW_MS - (now - messageTimestamps[0]);
      updateLimitStatus();
      addMessage(`Message limit reached. Please try again in ${formatTime(resetInMs)}.`, 'ai', 'Limit');
      return;
    }

    if (now < cooldownUntil) {
      const secondsLeft = Math.ceil((cooldownUntil - now) / 1000);
      updateLimitStatus();
      addMessage(`Please wait ${secondsLeft}s before sending another message.`, 'ai', 'Cooldown');
      return;
    }

    // Add user message to chat
    messageTimestamps.push(now);
    updateLimitStatus();
    addMessage(message, 'user');
    userInput.value = '';
    setLoading(true);

    try {
      console.log("📡 Attempting to call AI API...");
      
      // Try the external server first
      const response = await callExternalAPI(message);
      
      if (response.success) {
        console.log("✅ Successfully received AI response");
        setBackendStatus('online');
        addMessage(response.reply, 'ai', 'yapBot');
        chatHistory.push(
          { role: 'user', content: message },
          { role: 'assistant', content: response.reply }
        );
      } else {
        // Fallback to local responses
        console.log("🔄 Using fallback response");
        setBackendStatus('offline');
        const fallbackResponse = getFallbackResponse(message);
        addMessage(fallbackResponse, 'ai', 'Offline Bot');
      }

    } catch (err) {
      console.error('❌ General error:', err);
      setBackendStatus('offline');
      const fallbackResponse = getFallbackResponse(message);
      addMessage(fallbackResponse, 'ai', 'Offline Bot');
    } finally {
      setLoading(false);
      startCooldown();
    }
  }

  function setBackendStatus(status) {
    backendStatus = status;
    if (!backendStatusBadge) return;

    backendStatusBadge.classList.remove('online', 'offline', 'checking', 'unknown');
    backendStatusBadge.classList.add(status);

    if (status === 'online') backendStatusBadge.textContent = 'Backend: Online';
    else if (status === 'offline') backendStatusBadge.textContent = 'Backend: Offline (fallback mode)';
    else if (status === 'checking') backendStatusBadge.textContent = 'Backend: Checking...';
    else backendStatusBadge.textContent = 'Backend: Unknown';

    if (reconnectBtn) {
      reconnectBtn.disabled = status === 'checking';
    }
  }

  async function pingBackend() {
    setBackendStatus('checking');
    const endpoint = `${currentServer}/api/openai`;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000);

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'ping', context: [] }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);
      setBackendStatus(response.ok ? 'online' : 'offline');
      return response.ok;
    } catch {
      setBackendStatus('offline');
      return false;
    }
  }

  async function callExternalAPI(message) {
    const endpoint = `${currentServer}/api/openai`;
    
    console.log("🌐 Calling endpoint:", endpoint);
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout (Render free tier cold start)

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ 
          message: message,
          context: chatHistory.slice(-6)
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      
      if (!data?.reply) {
        throw new Error('Invalid response format');
      }

      return { success: true, reply: data.reply };

    } catch (error) {
      console.error('❌ API call failed:', error);
      
      // Try next server if available
      const currentIndex = servers.indexOf(currentServer);
      if (currentIndex < servers.length - 1) {
        currentServer = servers[currentIndex + 1];
        console.log(`🔄 Switching to server: ${currentServer}`);
        return callExternalAPI(message); // Retry with next server
      }
      
      return { success: false, error: error.message };
    }
  }

  function getFallbackResponse(message) {
    const lowerMessage = message.toLowerCase();
    
    // Smart fallback responses based on message content
    if (lowerMessage.includes('hello') || lowerMessage.includes('hi') || lowerMessage.includes('hey')) {
      return "Hello! I'm currently in offline mode. When the AI service is available, I can help with creative writing, coding, analysis, and much more!";
    }
    else if (lowerMessage.includes('weather')) {
      return "I can't check real-time weather data right now, but I can tell you that sunny days are great for outdoor activities!";
    }
    else if (lowerMessage.includes('joke') || lowerMessage.includes('funny')) {
      const jokes = [
        "Why don't scientists trust atoms? Because they make up everything!",
        "Why did the scarecrow win an award? He was outstanding in his field!",
        "What do you call a fake noodle? An impasta!"
      ];
      return jokes[Math.floor(Math.random() * jokes.length)];
    }
    else if (lowerMessage.includes('help')) {
      return "I'd love to help! While I'm in offline mode, I can provide general information and examples. For AI-powered responses, the external service needs to be available.";
    }
    else if (lowerMessage.includes('code') || lowerMessage.includes('programming')) {
      return "Here's a simple Python example:\n\n```python\n# Hello World in Python\nprint('Hello, World!')\n```\nWhen online, I can help with more complex programming questions!";
    }
    else {
      const genericResponses = [
        "That's an interesting question! While I'm currently in offline mode, I can tell you that AI systems typically process such queries by analyzing patterns in data to generate relevant responses.",
        "I appreciate your message! The AI service is temporarily unavailable, but I can provide general information on many topics.",
        "Great question! When the AI service is working, it can provide detailed answers on topics like this by drawing from vast amounts of training data.",
        "I'd love to help with that! Currently operating in limited mode - the full AI capabilities will be available when the service connection is restored."
      ];
      return genericResponses[Math.floor(Math.random() * genericResponses.length)];
    }
  }

  function addMessage(content, sender, modelName = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    
    const modelDisplay = sender === 'ai' && modelName 
      ? `<div class="model-indicator">🤖 ${modelName}</div>` 
      : '';

    const messageContent = sender === 'user' 
      ? `<div class="message-content" style="background: #007bff; color: white; border-bottom-right-radius: 5px; padding: 10px; margin: 5px 0;">
           ${escapeHtml(content)}
         </div>`
      : `<div class="message-content" style="background: white; border: 1px solid #e0e0e0; border-bottom-left-radius: 5px; padding: 10px; margin: 5px 0;">
           ${modelDisplay}
           ${escapeHtml(content)}
         </div>`;

    messageDiv.innerHTML = messageContent;
    chatMessages.appendChild(messageDiv);
    scrollToBottom();
  }

  function setLoading(loading) {
    isLoading = loading;
    generateBtn.disabled = loading;
    generateBtn.classList.toggle('cooldown', false);
    generateBtn.textContent = loading ? 'Sending...' : 'Send It';
    
    if (loading) {
      const typingDiv = document.createElement('div');
      typingDiv.className = 'message ai-message';
      typingDiv.id = 'typing-indicator';
      typingDiv.innerHTML = `
        <div class="message-content" style="background: white; border: 1px solid #e0e0e0; border-bottom-left-radius: 5px; padding: 10px; margin: 5px 0;">
          <div class="model-indicator">🤖 Thinking...</div>
          <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>
      `;

      chatMessages.appendChild(typingDiv);
      scrollToBottom();
    } else {
      const typingIndicator = document.getElementById('typing-indicator');
      if (typingIndicator) {
        typingIndicator.remove();
      }
    }
  }

  function startCooldown() {
    cooldownUntil = Date.now() + COOLDOWN_MS;
    generateBtn.disabled = true;
    generateBtn.classList.add('cooldown');
    updateLimitStatus();
    startStatusTimer();

    const intervalId = setInterval(() => {
      const remaining = cooldownUntil - Date.now();
      updateLimitStatus();
      if (remaining <= 0) {
        clearInterval(intervalId);
        generateBtn.disabled = false;
        generateBtn.classList.remove('cooldown');
        generateBtn.textContent = 'Send It';
        updateLimitStatus();
        return;
      }

      generateBtn.textContent = `Cooldown ${Math.ceil(remaining / 1000)}s`;
    }, 250);
  }

  function startStatusTimer() {
    if (statusTimerId) return;

    statusTimerId = setInterval(() => {
      updateLimitStatus();

      const hasActiveMessages = messageTimestamps.length > 0;
      const isCoolingDown = Date.now() < cooldownUntil;
      if (!hasActiveMessages && !isCoolingDown) {
        clearInterval(statusTimerId);
        statusTimerId = null;
      }
    }, 250);
  }

  function pruneMessageTimestamps(now = Date.now()) {
    messageTimestamps = messageTimestamps.filter(timestamp => now - timestamp < LIMIT_WINDOW_MS);
  }

  function updateLimitStatus() {
    if (!chatLimitStatus) return;

    const now = Date.now();
    pruneMessageTimestamps(now);

    const messagesLeft = Math.max(0, MAX_MESSAGES_PER_WINDOW - messageTimestamps.length);
    const cooldownRemaining = Math.max(0, cooldownUntil - now);

    const resetInMs = messageTimestamps.length > 0
      ? LIMIT_WINDOW_MS - (now - messageTimestamps[0])
      : LIMIT_WINDOW_MS;

    let statusText = `${messagesLeft} / ${MAX_MESSAGES_PER_WINDOW} left • Rate limit window: ${formatPreciseTime(LIMIT_WINDOW_MS)} • Ready`;
    chatLimitStatus.classList.remove('warning', 'limited');

    if (messagesLeft === 0 && !hasTriggeredLimitEgg) {
      hasTriggeredLimitEgg = true;
      addMessage('🥚 Easter Egg armed! Secret codes: "yapvibes" or "supernova". Type one now for a full-screen blast until reset.', 'ai', 'yapBot Secret');
    } else if (messagesLeft > 0) {
      hasTriggeredLimitEgg = false;
    }

    if (messagesLeft === 0 && messageTimestamps.length > 0) {
      statusText = `0 / ${MAX_MESSAGES_PER_WINDOW} left • Rate limit resets in ${formatPreciseTime(resetInMs)}`;
      chatLimitStatus.classList.add('limited');
    } else if (cooldownRemaining > 0) {
      statusText = `${messagesLeft} / ${MAX_MESSAGES_PER_WINDOW} left • Anti-spam cooldown ${(cooldownRemaining / 1000).toFixed(3)}s • Rate limit reset ${formatPreciseTime(resetInMs)}`;
      chatLimitStatus.classList.add('warning');
    } else if (messageTimestamps.length > 0) {
      statusText = `${messagesLeft} / ${MAX_MESSAGES_PER_WINDOW} left • Rate limit reset ${formatPreciseTime(resetInMs)}`;
    } else if (messagesLeft <= 3) {
      chatLimitStatus.classList.add('warning');
    }

    chatLimitStatus.textContent = statusText;
  }

  function formatTime(ms) {
    const totalSeconds = Math.max(0, Math.ceil(ms / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
  }

  function formatPreciseTime(ms) {
    const safeMs = Math.max(0, Math.ceil(ms));
    const minutes = Math.floor(safeMs / 60000);
    const seconds = Math.floor((safeMs % 60000) / 1000);
    const milliseconds = safeMs % 1000;
    return `${minutes}:${String(seconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`;
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function escapeHtml(unsafe) {
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function triggerFullscreenExplosion(mode = 'fire') {
    if (isExplosionActive) return;
    isExplosionActive = true;

    const now = Date.now();
    pruneMessageTimestamps(now);
    const resetInMs = messageTimestamps.length > 0
      ? Math.max(0, LIMIT_WINDOW_MS - (now - messageTimestamps[0]))
      : LIMIT_WINDOW_MS;

    const overlay = document.createElement('div');
    const isNova = mode === 'nova';
    overlay.style.cssText = `
      position: fixed;
      inset: 0;
      z-index: 99999;
      pointer-events: none;
      background: ${isNova
        ? 'radial-gradient(circle at center, rgba(80,180,255,0.86) 0%, rgba(80,80,255,0.55) 35%, rgba(4,4,24,0.92) 100%)'
        : 'radial-gradient(circle at center, rgba(255,120,0,0.85) 0%, rgba(255,40,0,0.55) 35%, rgba(10,0,0,0.92) 100%)'};
      animation: yapExplosionFlash 1500ms ease-out infinite alternate;
      overflow: hidden;
    `;

    for (let i = 0; i < 18; i++) {
      const blast = document.createElement('div');
      const size = 80 + Math.random() * 260;
      blast.style.cssText = `
        position:absolute;
        left:${Math.random() * 100}%;
        top:${Math.random() * 100}%;
        width:${size}px;
        height:${size}px;
        border-radius:50%;
        transform:translate(-50%, -50%);
        background: ${isNova
          ? 'radial-gradient(circle, rgba(220,245,255,0.95) 0%, rgba(120,170,255,0.82) 45%, rgba(100,120,255,0) 75%)'
          : 'radial-gradient(circle, rgba(255,255,180,0.95) 0%, rgba(255,120,0,0.82) 45%, rgba(255,0,0,0) 75%)'};
        animation: yapExplosionPulse ${700 + Math.random() * 900}ms ease-out infinite;
      `;
      overlay.appendChild(blast);
    }

    if (!document.getElementById('yap-explosion-style')) {
      const style = document.createElement('style');
      style.id = 'yap-explosion-style';
      style.textContent = `
        @keyframes yapExplosionFlash {
          0% { opacity: 0; transform: scale(0.95); }
          15% { opacity: 1; transform: scale(1.02); }
          100% { opacity: 0; transform: scale(1); }
        }
        @keyframes yapExplosionPulse {
          0% { opacity: 1; transform: translate(-50%, -50%) scale(0.2); }
          100% { opacity: 0; transform: translate(-50%, -50%) scale(2.6); }
        }
      `;
      document.head.appendChild(style);
    }

    document.body.appendChild(overlay);
    activeExplosionOverlay = overlay;
    document.body.style.animation = 'screenShake 0.8s ease-in-out 2';

    if (explosionCleanupTimeoutId) {
      clearTimeout(explosionCleanupTimeoutId);
    }

    explosionCleanupTimeoutId = setTimeout(() => {
      if (activeExplosionOverlay) {
        activeExplosionOverlay.remove();
        activeExplosionOverlay = null;
      }
      document.body.style.animation = '';
      isExplosionActive = false;
      explosionCleanupTimeoutId = null;
    }, resetInMs || LIMIT_WINDOW_MS);
  }

  // Initialize
  console.log("✅ AI Generator Ready - Enhanced Error Handling");
}
