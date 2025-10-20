// Main initialization script for projects page
import { initAIGenerator } from './ai-generator.js';
import { initNuclearEgg } from './nuclear-egg.js';
import { initGameLoader } from './game-loader.js';

class ProjectsMain {
  constructor() {
    this.componentsLoaded = false;
    this.modulesInitialized = false;
  }

  async init() {
    console.log("🚀 Initializing Projects Page...");
    
    try {
      // Load components
      await this.loadComponents();
      
      // Wait for components to render in DOM
      await new Promise(resolve => setTimeout(resolve, 300));
      
      // Initialize modules
      await this.initModules();
      
      this.componentsLoaded = true;
      console.log("✅ Projects page fully initialized");
    } catch (error) {
      console.error("❌ Error initializing projects page:", error);
    }
  }

  async loadComponents() {
    const components = [
      { id: 'header-container', url: 'components/header.html' },
      { id: 'game-section-container', url: 'components/game-section.html' },
      { id: 'ai-generator-container', url: 'components/ai-generator.html' }
    ];

    for (const component of components) {
      try {
        const response = await fetch(component.url);
        if (!response.ok) throw new Error(`Failed to load ${component.url}`);
        
        const html = await response.text();
        document.getElementById(component.id).innerHTML = html;
        console.log(`✅ Loaded ${component.url}`);
      } catch (error) {
        console.error(`❌ Failed to load ${component.url}:`, error);
      }
    }
  }

  async initModules() {
    console.log("🔄 Initializing modules with delays...");
    
    // Initialize Game Loader first (simpler)
    console.log("🎮 Initializing Game Loader...");
    setTimeout(() => {
      try {
        window.gameLoader = initGameLoader();
        if (window.gameLoader) {
          console.log("✅ Game Loader initialized");
        } else {
          console.error("❌ Game Loader returned null");
        }
      } catch (error) {
        console.error("❌ Failed to initialize Game Loader:", error);
      }
    }, 400);

    // Initialize Nuclear Easter Egg
    console.log("☢️ Initializing Nuclear Easter Egg...");
    setTimeout(() => {
      try {
        initNuclearEgg();
        console.log("✅ Nuclear Easter Egg initialized");
      } catch (error) {
        console.error("❌ Failed to initialize Nuclear Easter Egg:", error);
      }
    }, 500);

    // Initialize AI Generator last (most complex)
    console.log("🤖 Initializing AI Generator...");
    setTimeout(() => {
      try {
        initAIGenerator('https://yappotamus.onrender.com');
        console.log("✅ AI Generator initialized");
      } catch (error) {
        console.error("❌ Failed to initialize AI Generator:", error);
      }
    }, 600);
  }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  console.log("📄 DOM Content Loaded");
  const projectsMain = new ProjectsMain();
  projectsMain.init();
});

// Fallback initialization if modules fail
window.addEventListener('load', () => {
  console.log("🖥️ Window Loaded");
  setTimeout(() => {
    // Check if buttons work, if not, add manual event listeners
    const loadGameBtn = document.getElementById('load-game-btn');
    const aiGeneratorBtn = document.getElementById('load-ai-generator');
    
    if (loadGameBtn && !loadGameBtn.onclick) {
      console.log("🔄 Adding manual event listener for game loader");
      loadGameBtn.addEventListener('click', () => {
        const preview = document.getElementById('game-preview');
        const embed = document.getElementById('game-embed');
        if (preview && embed) {
          preview.style.display = 'none';
          embed.style.display = 'block';
        }
      });
    }
    
    if (aiGeneratorBtn && !aiGeneratorBtn.onclick) {
      console.log("🔄 Adding manual event listener for AI generator");
      aiGeneratorBtn.addEventListener('click', () => {
        const panel = document.getElementById('ai-generator-panel');
        if (panel) {
          const isVisible = panel.style.display === 'block';
          panel.style.display = isVisible ? 'none' : 'block';
          aiGeneratorBtn.textContent = isVisible ? 'Open Generator' : 'Close Generator';
        }
      });
    }
  }, 2000);
});