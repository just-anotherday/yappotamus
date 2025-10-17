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

app.use(
  cors({
    origin: ["https://just-anotherday.github.io", "http://localhost:3000"],
    methods: ["GET", "POST", "OPTIONS"],
    allowedHeaders: ["Content-Type","Authorization"],
  })
);

// Handling preflight (OPTIONS) requests
app.options('/ai', cors());

// Middleware
app.use(express.json());

// Route to check backend
app.get('/', (req, res) => {
  res.send('AI Generator Backend is Running');
});

const MAX_PROMPT_LENGTH = 200;
const BAD_WORDS = ['spam', 'hack', 'attack', 'malicious', 'virus', 'exploit']; // Add more as needed

// Global request counter (as backup)
let requestCount = 0;
setInterval(() => { requestCount = 0; }, 60_000);

app.post('/ai', rateLimit(60000, 5), async (req, res) => { // 5 requests per minute per IP
  // Global rate limit as backup
  if (requestCount >= 100) { // Global limit of 100 requests per minute
    return res.status(429).json({ error: "Service temporarily overloaded. Try again later." });
  }
  requestCount++;

  const { prompt } = req.body;
  
  // Input validation
  if (!prompt || typeof prompt !== 'string') {
    return res.status(400).json({ error: "Invalid prompt." });
  }
  
  if (prompt.length > MAX_PROMPT_LENGTH) {
    return res.status(400).json({ error: `Prompt too long. Max ${MAX_PROMPT_LENGTH} characters.` });
  }

  if (prompt.length < 3) {
    return res.status(400).json({ error: "Prompt must be at least 3 characters long." });
  }
  
  // Basic content filtering
  const lowerPrompt = prompt.toLowerCase();
  if (BAD_WORDS.some(word => lowerPrompt.includes(word))) {
    return res.status(400).json({ error: "Prompt contains blocked content." });
  }
  
  // Check for excessive repetition
  if (/(.)\1{10,}/.test(prompt)) {
    return res.status(400).json({ error: "Prompt contains excessive repetition." });
  }
  
  // Check for URL spam
  const urlRegex = /(http|https):\/\/[^\s]+/g;
  if ((prompt.match(urlRegex) || []).length > 2) {
    return res.status(400).json({ error: "Too many URLs in prompt." });
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
        max_tokens: 100, // Reduced from 150 to control costs
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
    console.error('AI generation error:', err);
    
    let safeError = "AI request failed. Please try again.";
    
    if (err.message.includes('rate limit')) {
      safeError = "Service temporarily unavailable. Please try again later.";
    } else if (err.message.includes('insufficient_quota')) {
      safeError = "Service quota exceeded. Please try again later.";
    } else if (err.message.includes('API key')) {
      safeError = "Service configuration error. Please contact administrator.";
    }
    
    res.status(500).json({ error: safeError });
  }
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`AI backend running on port ${PORT}`));