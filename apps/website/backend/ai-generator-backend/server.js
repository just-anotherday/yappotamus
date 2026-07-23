import express from 'express';
import fetch from 'node-fetch';
import cors from 'cors';
import dotenv from 'dotenv';
import rateLimit from 'express-rate-limit';

dotenv.config();

const app = express();
app.set('trust proxy', 1);

const HOST = process.env.HOST || '0.0.0.0';
const PORT = Number.parseInt(process.env.PORT || '5000', 10);
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const OPENAI_MODEL = process.env.OPENAI_MODEL || 'gpt-4o-mini';
const OPENAI_TIMEOUT_MS = Number.parseInt(process.env.OPENAI_TIMEOUT_MS || '25000', 10);
const MAX_PROMPT_LENGTH = 200;
const MAX_CONTEXT_MESSAGES = 6;
const MAX_CONTEXT_MESSAGE_LENGTH = 500;
const ALLOWED_CONTEXT_ROLES = new Set(['user', 'assistant']);
const ALLOWED_ORIGINS = new Set([
  'http://localhost:3000',
  'http://localhost:5173',
  'https://yapvibes.com',
  'https://www.yapvibes.com',
  'https://projects.yapvibes.com',
  'https://stocks.yapvibes.com'
]);

// Rate limiting for public, unsaved chatbot usage.
// In-memory is suitable for one Railway replica. Use a shared store when scaling.
const aiLimiter = rateLimit({
  windowMs: 60 * 1000,
  limit: 10,
  standardHeaders: 'draft-8',
  legacyHeaders: false,
  message: {
    error: 'Too many chat requests. Please wait up to 60 seconds and try again.'
  }
});

app.use(cors({
  origin: [...ALLOWED_ORIGINS],
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

const validateContext = (context) => {
  if (!Array.isArray(context)) {
    return 'Context must be an array.';
  }

  if (context.length > MAX_CONTEXT_MESSAGES) {
    return `Context may contain at most ${MAX_CONTEXT_MESSAGES} messages.`;
  }

  const isValid = context.every((entry) => (
    entry
    && typeof entry === 'object'
    && ALLOWED_CONTEXT_ROLES.has(entry.role)
    && typeof entry.content === 'string'
    && entry.content.length >= 1
    && entry.content.length <= MAX_CONTEXT_MESSAGE_LENGTH
  ));

  return isValid ? null : 'Context contains an invalid message.';
};

const requestCompletion = async (messages, maxTokens) => {
  if (!OPENAI_API_KEY) {
    throw new Error('API key is not configured');
  }

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: OPENAI_MODEL,
      messages,
      max_tokens: maxTokens,
      temperature: 0.7
    }),
    signal: AbortSignal.timeout(OPENAI_TIMEOUT_MS)
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    console.error('OpenAI API request failed with status:', response.status);
    throw new Error(errorData?.error?.code || `OpenAI API error (${response.status})`);
  }

  return response.json();
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

  const contextValidationError = validateContext(context);
  if (contextValidationError) {
    return res.status(400).json({ error: contextValidationError });
  }

  try {
    // Build messages array with context
    const messages = [
      ...context,
      { role: "user", content: message }
    ];

    const data = await requestCompletion(messages, 150);
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
    const data = await requestCompletion([{ role: 'user', content: prompt }], 100);
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

app.listen(PORT, HOST, () => {
  console.log(`AI backend listening on ${HOST}:${PORT}`);
});