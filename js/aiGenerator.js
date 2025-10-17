// Multi-Model AI Generator with Chat Interface
export function initAIGenerator(serverUrl = 'https://yappotamus.onrender.com') {
  const loadBtn = document.getElementById('load-ai-generator');
  const generateBtn = document.getElementById('generate-ai');
  const panel = document.getElementById('ai-generator-panel');
  const userInput = document.getElementById('user-input');
  const chatMessages = document.getElementById('chat-messages');
  const modelSelect = document.getElementById('model-select');
  const modelBadge = document.getElementById('current-model-badge');

  if (!loadBtn || !generateBtn || !panel || !userInput || !chatMessages) {
    console.error("Missing AI generator elements");
    return;
  }

  let currentModel = 'openai';
  let chatHistory = [];
  let isLoading = false;

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
  
  userInput.addEventListener('keypress', (e) => {
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
    const message = userInput.value.trim();
    if (!message || isLoading) return;

    addMessage(message, 'user');
    userInput.value = '';
    setLoading(true);

    try {
      const endpoint = `${serverUrl}/api/${currentModel}`;
      const response = await callAIAPI(message, endpoint);
      addMessage(response, 'ai', getModelName());
    } catch (err) {
      console.error('AI API Error:', err);
      addMessage('Sorry, I encountered an error. Please try again.', 'ai', 'System');
    }

    setLoading(false);
  }

  async function callAIAPI(message, endpoint) {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        message: message,
        context: chatHistory.slice(-6)
      })
    });

    const data = await res.json();
    
    if (!res.ok) {
      throw new Error(data?.error || `Request failed: ${res.status}`);
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
    
    const modelDisplay = sender === 'ai' && modelName 
      ? `<div class="model-indicator">${modelName}</div>` 
      : '';

    messageDiv.innerHTML = `
      <div class="message-content">
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