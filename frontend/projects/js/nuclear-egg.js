// Nuclear Easter Egg
export function initNuclearEgg() {
  console.log("☢️ Initializing Nuclear Easter Egg...");
  
  let clickCount = 0, easterEggActive = false;
  const image = document.querySelector('.project-image');

  if (!image) {
    console.log("❌ Project image not found for nuclear easter egg");
    return;
  }

  image.addEventListener('click', function(e) {
    if (easterEggActive) return;
    clickCount++;
    
    // Visual feedback for each click
    this.style.transform = `scale(${0.5 + (clickCount * 0.02)}) rotate(${clickCount % 2 === 0 ? '2deg' : '-2deg'})`;
    
    // Small confetti on each click
    if (typeof confetti === 'function') {
      confetti({
        particleCount: 15,
        spread: 25,
        origin: { y: 0.7 },
        colors: ['#FF6B6B', '#FFD166']
      });
    }
    
    // Show click counter
    updateClickCounter(clickCount);
    
    if (clickCount === 11) {
      triggerNuclearExplosion(e.clientX, e.clientY);
      easterEggActive = true;
    }
  });

  function updateClickCounter(count) {
    let counter = document.getElementById('click-counter');
    if (!counter) {
      counter = document.createElement('div');
      counter.id = 'click-counter';
      counter.className = 'click-counter';
      document.body.appendChild(counter);
    }
    
    counter.textContent = `Clicks: ${count}/11`;
    counter.style.display = 'block';
    
    // Hide counter after 2 seconds if not at 11
    if (count < 11) {
      setTimeout(() => {
        counter.style.display = 'none';
      }, 2000);
    }
  }

  function triggerNuclearExplosion(x, y) {
    console.log("💥 NUCLEAR DETONATION INITIATED!");
    
    // Hide counter
    document.getElementById('click-counter').style.display = 'none';
    
    // Nuclear explosion on image
    image.style.animation = 'nuclearExplodePhase1 0.5s forwards';
    
    // Create explosion layers
    setTimeout(() => createExplosionLayer(x, y, '#FF6B6B', 200), 100);
    setTimeout(() => createExplosionLayer(x, y, '#FFD166', 300), 200);
    setTimeout(() => createExplosionLayer(x, y, '#4ECDC4', 400), 300);
    setTimeout(() => createExplosionLayer(x, y, '#118AB2', 500), 400);
    
    // Screen effects
    document.body.style.animation = 'screenShake 1s infinite';
    setTimeout(() => document.body.style.filter = 'invert(1) hue-rotate(180deg)', 800);
    
    // Additional effects
    setTimeout(createMatrixRain, 1000);
    setTimeout(confettiNuke, 1500);
    setTimeout(playExplosionSounds, 500);
    setTimeout(createEmergencyLights, 1200);
    setTimeout(() => { document.body.style.animation = 'pageSpin 1s linear infinite'; }, 1000);
    setTimeout(createEmojiExplosion, 1500);
    
    // Show emergency warning
    showEmergencyWarning();
    
    // Reset after 5 seconds
    setTimeout(resetNuclearExplosion, 5000);
  }

  function createExplosionLayer(x, y, color, size) {
    const explosion = document.createElement('div');
    explosion.style.cssText = `
      position:fixed;top:${y}px;left:${x}px;width:${size}px;height:${size}px;
      background:radial-gradient(circle, ${color} 0%, transparent 70%);
      border-radius:50%;pointer-events:none;z-index:10000;
      animation:explosionPulse 0.8s ease-out forwards;transform:translate(-50%,-50%);
    `;
    document.body.appendChild(explosion);
    setTimeout(() => explosion.remove(), 800);
  }

  function createMatrixRain() {
    const chars = '01010101010101010101';
    for (let i = 0; i < 50; i++) {
      setTimeout(() => {
        const matrixChar = document.createElement('div');
        matrixChar.textContent = chars[Math.floor(Math.random()*chars.length)];
        matrixChar.style.cssText = `
          position:fixed;top:-20px;left:${Math.random()*100}vw;color:#00ff00;
          font-size:20px;font-family:monospace;z-index:9999;
          animation:matrixFall ${1+Math.random()*2}s linear forwards;
          pointer-events:none;
        `;
        document.body.appendChild(matrixChar);
        setTimeout(() => matrixChar.remove(), 3000);
      }, i*100);
    }
  }

  function confettiNuke() {
    for (let i=0; i<10; i++) {
      setTimeout(() => {
        confetti({
          particleCount:200, 
          spread:360,
          origin:{x:Math.random(),y:Math.random()},
          colors:['#FF6B6B','#4ECDC4','#FFD166','#118AB2','#FFC904','#00ff00'],
          startVelocity:50+Math.random()*50
        });
      }, i*200);
    }
  }

  function playExplosionSounds() {
    const sounds = [
      'https://assets.mixkit.co/sfx/preview/mixkit-explosion-video-game-sound-3120.mp3',
      'https://assets.mixkit.co/sfx/preview/mixkit-bomb-explosion-in-the-air-2800.mp3',
      'https://assets.mixkit.co/sfx/preview/mixkit-alarm-siren-1003.mp3'
    ];
    sounds.forEach((sound, index) => {
      setTimeout(() => {
        const audio = new Audio(sound);
        audio.volume = 0.3;
        audio.play().catch(e => console.log('Audio play failed:', e));
      }, index*500);
    });
  }

  function createEmergencyLights() {
    const lights = document.createElement('div');
    lights.style.cssText = `
      position:fixed;top:0;left:0;width:100%;height:100%;
      background:radial-gradient(circle, rgba(255,0,0,0.3) 0%, transparent 70%);
      pointer-events:none;z-index:9998;animation:emergencyFlash 0.3s infinite;
      mix-blend-mode:overlay;
    `;
    document.body.appendChild(lights);
    setTimeout(() => lights.remove(), 3000);
  }

  function showEmergencyWarning() {
    let warning = document.getElementById('emergency-warning');
    if (!warning) {
      warning = document.createElement('div');
      warning.id = 'emergency-warning';
      warning.className = 'emergency-warning';
      warning.innerHTML = `
        <div>🚨 CRITICAL ERROR 🚨</div>
        <div style="font-size: 0.5em; margin-top: 20px;">NUCLEAR DETONATION DETECTED</div>
      `;
      document.body.appendChild(warning);
    }
    warning.style.display = 'flex';
    warning.style.animation = 'emergencyFlash 0.5s infinite';
  }

  function createEmojiExplosion() {
    const emojis = ['💥','🔥','💣','☢️','⚡','🎆','💫','🌟','😱','🚨'];
    for (let i=0;i<30;i++) {
      setTimeout(() => {
        const emoji = document.createElement('div');
        emoji.textContent = emojis[Math.floor(Math.random()*emojis.length)];
        emoji.style.cssText = `
          position:fixed;top:${Math.random()*100}vh;left:${Math.random()*100}vw;
          font-size:${20+Math.random()*30}px;z-index:9999;
          animation:emojiFloat ${2+Math.random()*3}s ease-out forwards;
          pointer-events:none;transform:translate(-50%,-50%);
        `;
        document.body.appendChild(emoji);
        setTimeout(() => emoji.remove(), 5000);
      }, i*100);
    }
  }

  function resetNuclearExplosion() {
    console.log("🔄 Resetting nuclear explosion...");
    
    // Reset image
    image.style.animation = '';
    image.style.transform = 'scale(0.5)';
    
    // Reset body effects
    document.body.style.animation = '';
    document.body.style.filter = '';
    
    // Hide warning
    const warning = document.getElementById('emergency-warning');
    if (warning) warning.style.display = 'none';
    
    // Reset counters
    clickCount = 0;
    easterEggActive = false;
    
    // Clean up any remaining elements
    document.querySelectorAll('div').forEach(el => {
      if(el.textContent==='0'||el.textContent==='1'||['💥','🔥','💣','☢️','⚡','🎆','💫','🌟','😱','🚨'].includes(el.textContent)){
        el.remove();
      }
    });
    
    console.log("✅ Nuclear explosion reset complete");
  }
}