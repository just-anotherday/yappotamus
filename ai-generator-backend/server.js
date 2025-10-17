import express from 'express';
import fetch from 'node-fetch';
import cors from 'cors';
import dotenv from 'dotenv';

dotenv.config();

const app = express();

// Rate limiting storage
const rateLimitStore = new Map();

// Enhanced rate limiting middleware
const rateLimit = (windowMs = 60000, maxRequests = 5) => {
  return (req, res, next) => {
    const clientIP = req.ip || req.connection.remoteAddress;
    const now = Date.now();
    
    if (!rateLimitStore.has(clientIP)) {
      rateLimitStore.set(clientIP, { count: 1, firstRequest: now });
    } else {
      const clientData = rateLimitStore.get(clientIP);
      
      // Reset if window has passed
      if (now - clientData.firstRequest > windowMs) {
        clientData.count = 1;
        clientData.firstRequest = now;
      } else {
        clientData.count++;
      }
      
      // Check if over limit
      if (clientData.count > maxRequests) {
        const resetTime = clientData.firstRequest + windowMs;
        return res.status(429).json({ 
          error: "Too many requests", 
          retryAfter: Math.ceil((resetTime - now) / 1000)
        });
      }
    }
    
    next();
  };
};

// Clean up old rate limit entries every minute
setInterval(() => {
  const now = Date.now();
  for (const [ip, data] of rateLimitStore.entries()) {
    if (now - data.firstRequest > 60000) {
      rateLimitStore.delete(ip);
    }
  }
}, 60000);

app.use(cors({
  origin: ["https://just-anotherday.github.io", "http://localhost:3000"],
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type","Authorization"],
}));

// Middleware
app.use(express.json());

// Route to check backend
app.get('/', (req, res) => {
  res.send('AI Generator Backend is Running - OpenAI Only');
});

const MAX_PROMPT_LENGTH = 200;
const BAD_WORDS = ['spam', 'hack', 'attack', 'malicious', 'virus', 'exploit'];

// Global request counter (as backup)
let requestCount = 0;
setInterval(() => { requestCount = 0; }, 60_000);

// Common validation function
const validatePrompt = (prompt) => {
  if (!prompt || typeof prompt !== 'string') {
    return "Invalid prompt.";
  }
  
  if (prompt.length > MAX_PROMPT_LENGTH) {
    return `Prompt too long. Max ${MAX_PROMPT_LENGTH} characters.`;
  }

  if (prompt.length < 3) {
    return "Prompt must be at least 3 characters long.";
  }
  
  // Basic content filtering
  const lowerPrompt = prompt.toLowerCase();
  if (BAD_WORDS.some(word => lowerPrompt.includes(word))) {
    return "Prompt contains blocked content.";
  }
  
  // Check for excessive repetition
  if (/(.)\1{10,}/.test(prompt)) {
    return "Prompt contains excessive repetition.";
  }
  
  // Check for URL spam
  const urlRegex = /(http|https):\/\/[^\s]+/g;
  if ((prompt.match(urlRegex) || []).length > 2) {
    return "Too many URLs in prompt.";
  }

  return null;
};

// Common error handling
const handleAPIError = (err, res) => {
  console.error('AI API error:', err);
  
  let safeError = "AI request failed. Please try again.";
  
  if (err.message.includes('rate limit') || err.message.includes('rate_limit')) {
    safeError = "Service temporarily unavailable. Please try again later.";
  } else if (err.message.includes('insufficient_quota') || err.message.includes('quota')) {
    safeError = "Service quota exceeded. Please try again later.";
  } else if (err.message.includes('API key') || err.message.includes('auth')) {
    safeError = "Service configuration error. Please contact administrator.";
  } else if (err.message.includes('model')) {
    safeError = "AI model temporarily unavailable. Please try another model.";
  }
  
  res.status(500).json({ error: safeError });
};

// OpenAI endpoint
app.post('/api/openai', rateLimit(60000, 5), async (req, res) => {
  // Global rate limit as backup
  if (requestCount >= 100) {
    return res.status(429).json({ error: "Service temporarily overloaded. Try again later." });
  }
  requestCount++;

  const { message, context = [] } = req.body;
  
  // Input validation
  const validationError = validatePrompt(message);
  if (validationError) {
    return res.status(400).json({ error: validationError });
  }

  try {
    // Build messages array with context
    const messages = [
      ...context,
      { role: "user", content: message }
    ];

    // OpenAI text completion
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: "gpt-3.5-turbo",
        messages: messages,
        max_tokens: 150,
        temperature: 0.7
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
      console.error('OpenAI API error:', errorData);
      throw new Error(errorData.error?.message || 'OpenAI API error');
    }

    const data = await response.json();
    console.log("OpenAI response received for message:", message.substring(0, 50) + '...');
    
    const reply = data.choices?.[0]?.message?.content || "No response generated.";

    // Log successful usage
    console.log(`OpenAI used by ${req.ip}: ${message.substring(0, 50)}...`);

    res.json({ reply });

  } catch (err) {
    handleAPIError(err, res);
  }
});

// Keep your existing /ai endpoint for backward compatibility
app.post('/ai', rateLimit(60000, 5), async (req, res) => {
  // Global rate limit as backup
  if (requestCount >= 100) {
    return res.status(429).json({ error: "Service temporarily overloaded. Try again later." });
  }
  requestCount++;

  const { prompt } = req.body;
  
  // Input validation
  const validationError = validatePrompt(prompt);
  if (validationError) {
    return res.status(400).json({ error: validationError });
  }

  try {
    // OpenAI text completion with tighter limits
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: "gpt-3.5-turbo",
        messages: [{ role: "user", content: prompt }],
        max_tokens: 100,
        temperature: 0.7
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
      console.error('OpenAI API error:', errorData);
      throw new Error(errorData.error?.message || 'OpenAI API error');
    }

    const data = await response.json();
    console.log("OpenAI response received for prompt:", prompt.substring(0, 50) + '...');
    
    const result = data.choices?.[0]?.message?.content || "No text returned";

    // Log successful usage
    console.log(`AI used by ${req.ip}: ${prompt.substring(0, 50)}...`);

    res.json({ result });

  } catch (err) {
    handleAPIError(err, res);
  }
});

// Health check endpoint to verify services
app.get('/health', async (req, res) => {
  const health = {
    status: 'ok',
    timestamp: new Date().toISOString(),
    services: {
      openai: 'unknown'
    }
  };

  // Check OpenAI
  try {
    const testResponse = await fetch('https://api.openai.com/v1/models', {
      headers: {
        'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
      }
    });
    health.services.openai = testResponse.ok ? 'healthy' : 'unhealthy';
  } catch {
    health.services.openai = 'unreachable';
  }

  res.json(health);
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`AI backend running on port ${PORT}`);
  console.log('Available endpoints:');
  console.log('  POST /api/openai - OpenAI GPT-3.5');
  console.log('  POST /ai - Legacy endpoint (OpenAI)');
  console.log('  GET /health - Service status');
});