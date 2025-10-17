// SlimeScraper Game Loader
export function loadGame() {
  const preview = document.getElementById('game-preview');
  const embed = document.getElementById('game-embed');
  const iframe = document.getElementById('game-iframe');

  preview.innerHTML = '<p>🔄 Loading game... (This may take 30-60 seconds)</p>';
  setTimeout(() => {
    iframe.src = "https://itch.io/embed-upload/15262394?color=333333";
    embed.style.display = 'block';
  }, 500);
}

export function unloadGame() {
  const preview = document.getElementById('game-preview');
  const embed = document.getElementById('game-embed');
  const iframe = document.getElementById('game-iframe');

  preview.innerHTML = `<div class="game-warning">
    <p>⚠️ <strong>Large File Warning</strong></p>
    <p>This WebGL game is ~25MB and may take time to load.</p>
    <p>Only load if you have a stable internet connection.</p>
  </div>
  <button class="load-game-btn" onclick="loadGame()">🎮 Click to Load Game</button>
  <p><small>WebGL Game - Click to load when ready</small></p>`;
  embed.style.display = 'none';
  iframe.src = "about:blank";
}
