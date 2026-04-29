const express = require('express');
const cors = require('cors');
const OpenAI = require('openai');
const config = require('./config');

const app = express();

// Initialize OpenAI client
const openai = new OpenAI({
    apiKey: config.openai.apiKey,
});

// Middleware
app.use(cors());
app.use(express.json());

// Health check endpoint
app.get('/api/health', (req, res) => {
    res.status(200).json({ status: 'ok' });
});

// Chat completion endpoint
app.post('/api/chat/completions', async (req, res) => {
    const { messages } = req.body;

    if (!config.openai.apiKey || config.openai.apiKey === 'your_openai_api_key_here') {
        return res.status(500).json({ error: 'OpenAI API key not configured. Please set OPENAI_API_KEY in your .env file.' });
    }

    try {
        const response = await openai.chat.completions.create({
            model: config.openai.model,
            messages: messages,
        });

        res.status(200).json(response);
    } catch (error) {
        console.error('OpenAI API Error:', error);
        res.status(500).json({ error: 'Internal server error', message: error.message });
    }
});

app.listen(config.port, () => {
    console.log(`Server running on port ${config.port}`);
    console.log(`Using OpenAI model: ${config.openai.model}`);
});