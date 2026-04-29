const express = require('express');
const cors = require('cors');
const { Configuration, Ollama } = require('@ollama/core');

const app = express();
const port = 3001;

// Middleware
app.use(cors());

// Initialize Ollama client
const ollama = new Ollama({
    base: 'http://localhost:1143',
});

// Health check endpoint
app.get('/api/health', (req, res) => {
    res.status(200).json({ status: 'ok' });
});

// Chat completion endpoint
app.post('/api/chat/completions', async (req, res) => {
    const { messages } = req.body;

    try {
        const response = await ollama.chat({
            model: 'llama2',
            messages,
        });

        res.status(200).json(response);
    } catch (error) {
        console.error('Error:', error);
        res.status(500).json({ error: 'Internal server error' });
    }
});

app.listen(port, () => {
    console.log(`Server running on port ${port}`);
});