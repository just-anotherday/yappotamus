export function initAIGenerator() {
  console.log("🚀 AI Generator Initializing...");
  
  const generateBtn = document.getElementById('generate-ai');
  const panel = document.getElementById('ai-generator-panel');
  const userInput = document.getElementById('user-input');
  const chatMessages = document.getElementById('chat-messages');
  const chatLimitStatus = document.getElementById('chat-limit-status');

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
  const COOLDOWN_MS = 4000;
  const LIMIT_WINDOW_MS = 3 * 60 * 1000;
  const MAX_MESSAGES_PER_WINDOW = 10;
  
  // Multiple server fallbacks
  const servers = [
    'https://yappotamus.onrender.com'
  ];
  
  let currentServer = servers[0];

  // Ensure panel is always visible
  panel.style.display = 'block';
  updateLimitStatus();
  startStatusTimer();

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
        addMessage(response.reply, 'ai', 'yapBot');
        chatHistory.push(
          { role: 'user', content: message },
          { role: 'assistant', content: response.reply }
        );
      } else {
        // Fallback to local responses
        console.log("🔄 Using fallback response");
        const fallbackResponse = getFallbackResponse(message);
        addMessage(fallbackResponse, 'ai', 'yapBot (Offline)');
      }

    } catch (err) {
      console.error('❌ General error:', err);
      const fallbackResponse = getFallbackResponse(message);
      addMessage(fallbackResponse, 'ai', 'yapBot (Offline)');
    } finally {
      setLoading(false);
      startCooldown();
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
          <div class="typing-indicator" style="display: inline-flex; align-items: center; gap: 3px;">
            <div class="typing-dot" style="width: 6px; height: 6px; border-radius: 50%; background: #999; animation: typing-bounce 1.4s infinite ease-in-out;"></div>
            <div class="typing-dot" style="width: 6px; height: 6px; border-radius: 50%; background: #999; animation: typing-bounce 1.4s infinite ease-in-out; animation-delay: -0.16s;"></div>
            <div class="typing-dot" style="width: 6px; height: 6px; border-radius: 50%; background: #999; animation: typing-bounce 1.4s infinite ease-in-out; animation-delay: -0.32s;"></div>
          </div>
        </div>
      `;
      
      if (!document.querySelector('#typing-animation')) {
        const style = document.createElement('style');
        style.id = 'typing-animation';
        style.textContent = `
          @keyframes typing-bounce {
            0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
            40% { transform: scale(1); opacity: 1; }
          }
        `;
        document.head.appendChild(style);
      }
      
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
    }, 50);
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

    let statusText = `${messagesLeft} / ${MAX_MESSAGES_PER_WINDOW} left • Rate limit window: 3:00.000 • Ready`;
    chatLimitStatus.classList.remove('warning', 'limited');

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

  // Initialize
  console.log("✅ AI Generator Ready - Enhanced Error Handling");
}
