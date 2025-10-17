// AI Generator
export function initAIGenerator(serverUrl = 'https://yappotamus.onrender.com/ai') {
  const loadBtn = document.getElementById('load-ai-generator');
  const generateBtn = document.getElementById('generate-ai');
  const panel = document.getElementById('ai-generator-panel');
  const promptInput = document.getElementById('ai-prompt');
  const typeSelect = document.getElementById('ai-type');
  const resultDiv = document.getElementById('ai-result');

  loadBtn.addEventListener('click', () => panel.style.display = 'block');

  generateBtn.addEventListener('click', async () => {
    const prompt = promptInput.value.trim();
    const type = typeSelect.value;
    if (!prompt) return alert("Please enter a prompt.");
    
    resultDiv.innerHTML = "<p>🔄 Generating...</p>";

    try {
      const res = await fetch(serverUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, type })
      });
      const data = await res.json();

      if (res.ok) {
        if (type === "image") {
          // Use full URL if needed
          const imageUrl = data.result.startsWith('/') 
            ? `${serverUrl.replace('/ai','')}${data.result}` 
            : data.result;
          resultDiv.innerHTML = `<img src="${imageUrl}" alt="AI result" style="max-width:90vw; border-radius:8px;" />`;
        } else {
          resultDiv.innerHTML = `<pre style="white-space:pre-wrap; font-family:monospace;">${data.result}</pre>`;
        }
      } else {
        resultDiv.innerHTML = `<p style="color:red;">Error: ${data.error}</p>`;
      }

    } catch (err) {
      resultDiv.innerHTML = `<p style="color:red;">Error: ${err.message}</p>`;
    }
  });
}
