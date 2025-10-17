// 3D Particle Background for all pages
function initThreeJSBackground() {
    // Check if WebGL is supported
    if (!window.WebGLRenderingContext) {
        console.log('WebGL not supported, using fallback background');
        createFallbackBackground();
        return;
    }

    try {
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({ 
            alpha: true,
            antialias: true 
        });
        
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.domElement.style.position = 'fixed';
        renderer.domElement.style.top = '0';
        renderer.domElement.style.left = '0';
        renderer.domElement.style.zIndex = '-1';
        renderer.domElement.style.pointerEvents = 'none';
        document.body.appendChild(renderer.domElement);

        // Create particles with custom movement
        const particles = new THREE.BufferGeometry();
        const particleCount = 800; // Reduced for better performance
        const posArray = new Float32Array(particleCount * 3);
        const velocityArray = new Float32Array(particleCount * 3);

        for(let i = 0; i < particleCount * 3; i++) {
            posArray[i] = (Math.random() - 0.5) * 15;
            velocityArray[i] = (Math.random() - 0.5) * 0.015;
        }

        particles.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
        particles.setAttribute('velocity', new THREE.BufferAttribute(velocityArray, 3));

        const particleMaterial = new THREE.PointsMaterial({
            size: 0.08,
            color: 0x3498db,
            transparent: true,
            opacity: 0.8
        });

        const particleMesh = new THREE.Points(particles, particleMaterial);
        scene.add(particleMesh);

        camera.position.z = 5;

        // Animation function
        function animate() {
            requestAnimationFrame(animate);

            const positions = particleMesh.geometry.attributes.position.array;
            const velocities = particleMesh.geometry.attributes.velocity.array;

            for (let i = 0; i < particleCount; i++) {
                positions[i * 3] += velocities[i * 3];
                positions[i * 3 + 1] += velocities[i * 3 + 1];
                positions[i * 3 + 2] += velocities[i * 3 + 2];

                // Bounce particles
                if (Math.abs(positions[i * 3]) > 7.5) velocities[i * 3] *= -1;
                if (Math.abs(positions[i * 3 + 1]) > 7.5) velocities[i * 3 + 1] *= -1;
                if (Math.abs(positions[i * 3 + 2]) > 7.5) velocities[i * 3 + 2] *= -1;
            }

            particleMesh.geometry.attributes.position.needsUpdate = true;
            particleMesh.rotation.x += 0.0005;
            particleMesh.rotation.y += 0.0005;
            
            renderer.render(scene, camera);
        }

        // Handle window resize
        function handleResize() {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }

        window.addEventListener('resize', handleResize);
        animate();

    } catch (error) {
        console.log('Three.js initialization failed, using fallback:', error);
        createFallbackBackground();
    }
}

// Fallback gradient background
function createFallbackBackground() {
    const fallbackBg = document.createElement('div');
    fallbackBg.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: linear-gradient(-45deg, #ee7752, #e73c7e, #23a6d5, #23d5ab);
        background-size: 400% 400%;
        animation: gradient 15s ease infinite;
        z-index: -1;
        pointer-events: none;
    `;
    
    // Add CSS for animation
    const style = document.createElement('style');
    style.textContent = `
        @keyframes gradient {
            0% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
            100% { background-position: 0% 50%; }
        }
    `;
    document.head.appendChild(style);
    document.body.appendChild(fallbackBg);
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Wait for Three.js to load
    if (typeof THREE !== 'undefined') {
        initThreeJSBackground();
    } else {
        // If Three.js fails to load, use fallback
        console.log('Three.js not loaded, using fallback background');
        createFallbackBackground();
    }
});

// Handle Three.js script loading failure
window.addEventListener('error', function(e) {
    if (e.target.src && e.target.src.includes('three.min.js')) {
        console.log('Three.js failed to load, using fallback background');
        createFallbackBackground();
    }
});