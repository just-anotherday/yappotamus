import express from 'express';
import fetch from 'node-fetch';
import cors from 'cors';
import dotenv from 'dotenv';
import rateLimit from 'express-rate-limit';

dotenv.config();

const app = express();
app.set('trust proxy', 1);

// Rate limiting for public, unsaved chatbot usage.
// In-memory is fine for a single Render instance. Use Redis if scaling horizontally.
const aiLimiter = rateLimit({
  windowMs: 3 * 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-8',
  legacyHeaders: false,
  message: {
    error: 'Too many chat requests. Please wait up to 3 minutes and try again.'
  }
});

app.use(cors({
  origin: ["https://just-anotherday.github.io", "https://www.just-anotherday.github.io", "http://localhost:3000", "https://yappotamus.onrender.com", "https://yapvibes.com", "https://www.yapvibes.com"],
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type","Authorization"],
  credentials: true,
  optionsSuccessStatus: 204
}));

// Middleware - limit body size to prevent large payload attacks (1kb max)
app.use(express.json({ limit: '1kb' }));
app.use(express.urlencoded({ extended: false, limit: '1kb' }));

// Root endpoint - simplified, no tech stack disclosure
app.get('/', (req, res) => {
  res.json({ status: 'ok' });
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

// Common error handling - don't expose sensitive details
const handleAPIError = (err, res) => {
  console.error('AI API error:', err.message);
  
  let safeError = "AI request failed. Please try again.";
  
  if (err.message.includes('rate limit') || err.message.includes('rate_limit')) {
    safeError = "Service temporarily unavailable. Please try again later.";
  } else if (err.message.includes('insufficient_quota') || err.message.includes('quota')) {
    safeError = "Service temporarily unavailable. Please try again later.";
  } else if (err.message.includes('API key') || err.message.includes('auth')) {
    safeError = "Service configuration error. Please contact administrator.";
  } else if (err.message.includes('model')) {
    safeError = "AI model temporarily unavailable. Please try again later.";
  }
  
  res.status(500).json({ error: safeError });
};

// OpenAI endpoint
app.post('/api/openai', aiLimiter, async (req, res) => {
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
        model: process.env.OPENAI_MODEL || "gpt-4o-mini",
        messages: messages,
        max_tokens: 150,
        temperature: 0.7
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
      console.error('OpenAI API error:', errorData?.error?.message);
      throw new Error(errorData?.error?.message || 'OpenAI API error');
    }

    const data = await response.json();
    const reply = data?.choices?.[0]?.message?.content || "No response generated.";

    res.json({ reply });

  } catch (err) {
    handleAPIError(err, res);
  }
});

// Legacy endpoint for backward compatibility
app.post('/ai', aiLimiter, async (req, res) => {
  if (requestCount >= 100) {
    return res.status(429).json({ error: "Service temporarily overloaded. Try again later." });
  }
  requestCount++;

  const { prompt } = req.body;
  
  const validationError = validatePrompt(prompt);
  if (validationError) {
    return res.status(400).json({ error: validationError });
  }

  try {
    const response = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL || "gpt-4o-mini",
        messages: [{ role: "user", content: prompt }],
        max_tokens: 100,
        temperature: 0.7
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
      console.error('OpenAI API error:', errorData?.error?.message);
      throw new Error(errorData?.error?.message || 'OpenAI API error');
    }

    const data = await response.json();
    const result = data?.choices?.[0]?.message?.content || "No text returned";

    res.json({ result });

  } catch (err) {
    handleAPIError(err, res);
  }
});

// Health check endpoint - protected with a secret key to prevent probing
const HEALTH_SECRET = process.env.HEALTH_SECRET || '';

app.get('/health', async (req, res) => {
  if (!HEALTH_SECRET) {
    return res.status(501).json({ error: 'Health checks not configured' });
  }

  const key = req.query?.key || '';
  if (key !== HEALTH_SECRET) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  // Return minimal info only - no service status disclosure
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString()
  });
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`AI backend running on port ${PORT}`);
});