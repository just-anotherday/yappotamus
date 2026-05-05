// Game loading functionality
export function initGameLoader() {
  console.log("🎮 Initializing Game Loader...");

  const loadBtn = document.getElementById('load-game-btn');
  const unloadBtn = document.getElementById('unload-game-btn');
  const preview = document.getElementById('game-preview');
  const embed = document.getElementById('game-embed');

  console.log("🔍 Game Loader Elements:", {
    loadBtn: !!loadBtn,
    unloadBtn: !!unloadBtn,
    preview: !!preview,
    embed: !!embed
  });

  if (!loadBtn || !unloadBtn || !preview || !embed) {
    console.error("❌ Game elements not found");
    console.log("Available elements:", {
      buttons: document.querySelectorAll('button'),
      gamePreview: document.getElementById('game-preview'),
      gameEmbed: document.getElementById('game-embed')
    });
    return null;
  }

  const gameLoader = {
    loadGame: function() {
      console.log("🎮 Loading game...");
      preview.style.display = 'none';
      embed.style.display = 'block';
      console.log("✅ Game loaded successfully");
      
      // Show loading feedback
      loadBtn.textContent = '🔄 Loading...';
      loadBtn.disabled = true;
      
      setTimeout(() => {
        loadBtn.textContent = '🎮 Click to Load Game';
        loadBtn.disabled = false;
      }, 2000);
    },

    unloadGame: function() {
      console.log("❌ Unloading game...");
      preview.style.display = 'block';
      embed.style.display = 'none';
      console.log("✅ Game unloaded successfully");
    }
  };

  // Remove any existing event listeners
  loadBtn.replaceWith(loadBtn.cloneNode(true));
  unloadBtn.replaceWith(unloadBtn.cloneNode(true));

  // Get fresh references after clone
  const freshLoadBtn = document.getElementById('load-game-btn');
  const freshUnloadBtn = document.getElementById('unload-game-btn');

  // Add event listeners
  freshLoadBtn.addEventListener('click', () => {
    console.log("🎯 Load Game button clicked!");
    gameLoader.loadGame();
  });

  freshUnloadBtn.addEventListener('click', () => {
    console.log("🎯 Unload Game button clicked!");
    gameLoader.unloadGame();
  });

  console.log("✅ Game Loader fully initialized with event listeners");
  return gameLoader;
}