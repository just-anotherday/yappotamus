// AI Generator
export function initAIGenerator(serverUrl = 'https://yappotamus.onrender.com/ai') {
  const loadBtn = document.getElementById('load-ai-generator');
  const generateBtn = document.getElementById('generate-ai');
  const panel = document.getElementById('ai-generator-panel');
  const promptInput = document.getElementById('ai-prompt');
  const typeSelect = document.getElementById('ai-type');
  const resultDiv = document.getElementById('ai-result');

  if (!loadBtn || !generateBtn || !panel || !promptInput || !typeSelect || !resultDiv) {
    console.error("Missing one or more AI generator elements in HTML.");
    return;
  }

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
        body: JSON.stringify({ prompt, type }),
        mode: "cors"
      });

      let data;
      try { data = await res.json(); }
      catch { data = null; }

      console.log("Response status:", res.status, "Data:", data);

      if (!res.ok) {
        const msg = data?.error || `Server returned status ${res.status}`;
        resultDiv.innerHTML = `<p style="color:red;">Error: ${msg}</p>`;
        return;
      }

      if (!data?.result) {
        resultDiv.innerHTML = `<p style="color:red;">No result returned.</p>`;
        return;
      }
      resultDiv.innerHTML = `<pre style="white-space:pre-wrap; font-family:monospace;">${data.result}</pre>`;

    } catch (err) {
      console.error(err);
      resultDiv.innerHTML = `<p style="color:red;">Error: ${err.message}</p>`;
    }
  });
}
