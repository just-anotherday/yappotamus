// Multi-Model AI Generator
export function initAIGenerator(serverUrl = 'https://yappotamus.onrender.com') {
  const loadBtn = document.getElementById('load-ai-generator');
  const generateBtn = document.getElementById('generate-ai');
  const panel = document.getElementById('ai-generator-panel');
  const promptInput = document.getElementById('ai-prompt');
  const resultDiv = document.getElementById('ai-result');

  if (!loadBtn || !generateBtn || !panel || !promptInput || !resultDiv) {
    console.error("Missing one or more AI generator elements in HTML.");
    return;
  }

  // Add model selection HTML dynamically if it doesn't exist
  if (!document.getElementById('model-select')) {
    const modelSelectorHTML = `
      <div class="model-selector-group" style="margin-bottom: 1rem;">
        <label for="model-select" style="display: block; margin-bottom: 0.5rem; font-weight: bold; color: #333;">
          Choose AI Model:
        </label>
        <div style="display: flex; align-items: center; gap: 15px;">
          <select id="model-select" class="model-select" style="padding: 8px 12px; border: 1px solid #ccc; border-radius: 5px; background: white;">
            <option value="openai">OpenAI GPT-3.5</option>
            <option value="deepseek">DeepSeek Chat</option>
          </select>
          <span id="current-model-badge" class="model-badge" style="padding: 5px 12px; border-radius: 15px; font-size: 0.8rem; font-weight: bold; color: white; background: #10a37f;">OpenAI GPT-3.5</span>
        </div>
      </div>
    `;
    
    // Insert model selector at the beginning of the panel
    panel.insertAdjacentHTML('afterbegin', modelSelectorHTML);
  }

  // Add chat messages container if it doesn't exist
  if (!document.getElementById('chat-messages')) {
    const chatContainerHTML = `
      <div class="ai-chat-container" style="border: 1px solid #e0e0e0; border-radius: 10px; background: white; overflow: hidden; margin-top: 1rem;">
        <div id="chat-messages" class="chat-messages" style="height: 250px; overflow-y: auto; padding: 20px; background: #f8f9fa; border-bottom: 1px solid #e0e0e0;">
          <div class="message ai-message" style="margin-bottom: 15px; display: flex; justify-content: flex-start;">
            <div class="message-content" style="max-width: 80%; padding: 12px 16px; border-radius: 15px; line-height: 1.4; font-size: 0.9rem; background: white; border: 1px solid #e0e0e0; border-bottom-left-radius: 5px;">
              <div class="model-indicator" style="font-size: 0.75em; color: #666; margin-bottom: 5px; font-weight: bold;">🤖 AI Assistant</div>
              Hello! I'm your AI assistant. Choose a model above and start chatting!
            </div>
          </div>
        </div>
      </div>
    `;
    
    // Insert chat container before the input group
    const inputGroup = panel.querySelector('.input-group');
    if (inputGroup) {
      inputGroup.insertAdjacentHTML('beforebegin', chatContainerHTML);
    }
  }

  // Get references to new elements
  const modelSelect = document.getElementById('model-select');
  const modelBadge = document.getElementById('current-model-badge');
  const chatMessages = document.getElementById('chat-messages');
  const userInput = document.getElementById('user-input') || promptInput; // Fallback to original input

  // State variables
  let currentModel = 'openai';
  let chatHistory = [];
  let isLoading = false;

  // Update the input area to use textarea if it's still an input
  if (promptInput.tagName === 'INPUT') {
    const textarea = document.createElement('textarea');
    textarea.id = 'user-input';
    textarea.placeholder = promptInput.placeholder;
    textarea.className = promptInput.className;
    textarea.rows = 3;
    textarea.style.width = '100%';
    textarea.style.marginBottom = '0.5rem';
    promptInput.replaceWith(textarea);
  }

  // Event listeners
  loadBtn.addEventListener('click', () => {
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    loadBtn.textContent = panel.style.display === 'block' ? 'Close Generator' : 'Open Generator';
  });

  modelSelect.addEventListener('change', (e) => {
    currentModel = e.target.value;
    updateModelBadge();
    addSystemMessage(`Switched to ${getModelName()} model`);
  });

  generateBtn.addEventListener('click', handleGenerate);
  
  // Use the textarea for input
  const userInputElement = document.getElementById('user-input') || promptInput;
  userInputElement.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleGenerate();
    }
  });

  function updateModelBadge() {
    const modelName = getModelName();
    modelBadge.textContent = modelName;
    modelBadge.style.background = currentModel === 'openai' ? '#10a37f' : '#3b82f6';
  }

  function getModelName() {
    return currentModel === 'openai' ? 'OpenAI GPT-3.5' : 'DeepSeek Chat';
  }

  async function handleGenerate() {
    const message = userInputElement.value.trim();
    if (!message || isLoading) return;

    // Add user message to chat
    addMessage(message, 'user');
    userInputElement.value = '';
    setLoading(true);

    try {
      const response = await callAIAPI(message);
      addMessage(response, 'ai', getModelName());
    } catch (err) {
      console.error('AI API Error:', err);
      addMessage('Sorry, I encountered an error. Please try again.', 'ai', 'System');
    }

    setLoading(false);
  }

  async function callAIAPI(message) {
    // Use your existing server URL structure but add model endpoint
    const endpoint = `${serverUrl}/api/${currentModel}`;
    
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { 
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ 
        message: message,
        context: chatHistory.slice(-6) // Keep last 3 exchanges
      }),
      mode: "cors"
    });

    let data;
    try { 
      data = await res.json(); 
    } catch { 
      data = null; 
    }

    console.log("Response status:", res.status, "Data:", data);

    if (!res.ok) {
      const msg = data?.error || `Server returned status ${res.status}`;
      throw new Error(msg);
    }

    if (!data?.reply) {
      throw new Error('No result returned from AI');
    }

    // Update chat history
    chatHistory.push(
      { role: 'user', content: message },
      { role: 'assistant', content: data.reply }
    );

    return data.reply;
  }

  function addMessage(content, sender, modelName = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}-message`;
    messageDiv.style.marginBottom = '15px';
    messageDiv.style.display = 'flex';
    messageDiv.style.justifyContent = sender === 'user' ? 'flex-end' : 'flex-start';

    const modelDisplay = sender === 'ai' && modelName 
      ? `<div class="model-indicator" style="font-size: 0.75em; color: #666; margin-bottom: 5px; font-weight: bold;">${modelName}</div>` 
      : '';

    const messageStyles = sender === 'user' 
      ? 'background: #007bff; color: white; border-bottom-right-radius: 5px;'
      : 'background: white; border: 1px solid #e0e0e0; border-bottom-left-radius: 5px;';

    messageDiv.innerHTML = `
      <div class="message-content" style="max-width: 80%; padding: 12px 16px; border-radius: 15px; line-height: 1.4; font-size: 0.9rem; ${messageStyles}">
        ${modelDisplay}
        ${escapeHtml(content)}
      </div>
    `;

    chatMessages.appendChild(messageDiv);
    scrollToBottom();
  }

  function addSystemMessage(content) {
    addMessage(content, 'ai', 'System');
  }

  function setLoading(loading) {
    isLoading = loading;
    generateBtn.disabled = loading;
    generateBtn.textContent = loading ? 'Generating...' : 'Generate Text';

    if (loading) {
      showTypingIndicator();
    } else {
      hideTypingIndicator();
    }
  }

  function showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message ai-message';
    typingDiv.id = 'typing-indicator';
    typingDiv.style.marginBottom = '15px';
    typingDiv.style.display = 'flex';
    typingDiv.style.justifyContent = 'flex-start';
    
    typingDiv.innerHTML = `
      <div class="message-content" style="max-width: 80%; padding: 12px 16px; border-radius: 15px; line-height: 1.4; font-size: 0.9rem; background: white; border: 1px solid #e0e0e0; border-bottom-left-radius: 5px;">
        <div class="model-indicator" style="font-size: 0.75em; color: #666; margin-bottom: 5px; font-weight: bold;">${getModelName()}</div>
        <div class="typing-indicator" style="display: inline-flex; align-items: center; gap: 3px;">
          <div class="typing-dot" style="width: 6px; height: 6px; border-radius: 50%; background: #999; animation: typing-bounce 1.4s infinite ease-in-out;"></div>
          <div class="typing-dot" style="width: 6px; height: 6px; border-radius: 50%; background: #999; animation: typing-bounce 1.4s infinite ease-in-out; animation-delay: -0.16s;"></div>
          <div class="typing-dot" style="width: 6px; height: 6px; border-radius: 50%; background: #999; animation: typing-bounce 1.4s infinite ease-in-out; animation-delay: -0.32s;"></div>
        </div>
      </div>
    `;

    // Add CSS animation if not already present
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
  }

  function hideTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
      typingIndicator.remove();
    }
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
  updateModelBadge();
}