// Simplified Multi-Model AI Generator (works with your current HTML)
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

  // Add model selection HTML dynamically
  if (!document.getElementById('model-select')) {
    const modelSelectorHTML = `
      <div style="margin-bottom: 1rem; padding: 15px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e0e0e0;">
        <label for="model-select" style="display: block; margin-bottom: 0.5rem; font-weight: bold; color: #333;">
          Choose AI Model:
        </label>
        <div style="display: flex; align-items: center; gap: 15px;">
          <select id="model-select" style="padding: 8px 12px; border: 1px solid #ccc; border-radius: 5px; background: white; flex: 1;">
            <option value="openai">OpenAI GPT-3.5</option>
            <option value="deepseek">DeepSeek Chat</option>
          </select>
          <span id="current-model-badge" style="padding: 5px 12px; border-radius: 15px; font-size: 0.8rem; font-weight: bold; color: white; background: #10a37f;">
            OpenAI GPT-3.5
          </span>
        </div>
      </div>
    `;
    panel.insertAdjacentHTML('afterbegin', modelSelectorHTML);
  }

  const modelSelect = document.getElementById('model-select');
  const modelBadge = document.getElementById('current-model-badge');
  let currentModel = 'openai';

  // Event listeners
  loadBtn.addEventListener('click', () => {
    const isVisible = panel.style.display === 'block';
    panel.style.display = isVisible ? 'none' : 'block';
    loadBtn.textContent = isVisible ? 'Open Generator' : 'Close Generator';
  });

  modelSelect.addEventListener('change', (e) => {
    currentModel = e.target.value;
    updateModelBadge();
  });

  generateBtn.addEventListener('click', handleGenerate);
  
  promptInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleGenerate();
    }
  });

  function updateModelBadge() {
    const modelName = currentModel === 'openai' ? 'OpenAI GPT-3.5' : 'DeepSeek Chat';
    modelBadge.textContent = modelName;
    modelBadge.style.background = currentModel === 'openai' ? '#10a37f' : '#3b82f6';
  }

  async function handleGenerate() {
    const prompt = promptInput.value.trim();
    if (!prompt) {
      alert("Please enter a prompt.");
      return;
    }

    // Show loading state
    generateBtn.disabled = true;
    generateBtn.textContent = 'Generating...';
    resultDiv.innerHTML = "<p>🔄 Generating AI response...</p>";

    try {
      // Choose the correct endpoint based on selected model
      const endpoint = `${serverUrl}/api/${currentModel}`;

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ 
          message: prompt,
          context: [] // Empty context for single generation
        })
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
        resultDiv.innerHTML = `<p style="color:red;">Error: ${msg}</p>`;
        return;
      }

      if (!data?.reply) {
        resultDiv.innerHTML = `<p style="color:red;">No result returned from AI.</p>`;
        return;
      }

      // Display the result with model badge
      resultDiv.innerHTML = `
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; border-left: 4px solid ${currentModel === 'openai' ? '#10a37f' : '#3b82f6'};">
          <div style="font-size: 0.8rem; color: #666; margin-bottom: 0.5rem; font-weight: bold;">
            ${currentModel === 'openai' ? 'OpenAI GPT-3.5' : 'DeepSeek Chat'}
          </div>
          <div style="white-space: pre-wrap; font-family: inherit; margin: 0; line-height: 1.5;">
            ${data.reply}
          </div>
        </div>
      `;

    } catch (err) {
      console.error('Generation error:', err);
      resultDiv.innerHTML = `<p style="color:red;">Error: ${err.message}</p>`;
    } finally {
      // Reset button state
      generateBtn.disabled = false;
      generateBtn.textContent = 'Generate Text';
    }
  }

  // Initialize
  updateModelBadge();
}