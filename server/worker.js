require('dotenv').config();

const openaiApiKey = process.env.OPENAI_API_KEY;
const model = 'gpt-3.5-turbo';

// Fetch interceptor for OpenAI API calls
async function handleFetch(request) {
    const url = new URL(request.url);
    
    // CORS preflight
    if (request.method === 'OPTIONS') {
        return new Response(null, {
            headers: {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            },
        });
    }

    // Health check
    if (url.pathname === '/api/health' && request.method === 'GET') {
        return new Response(JSON.stringify({ status: 'ok' }), {
            headers: { 'Content-Type': 'application/json' },
        });
    }

    // Chat completions
    if (url.pathname === '/api/chat/completions' && request.method === 'POST') {
        if (!openaiApiKey || openaiApiKey === 'your_openai_api_key_here') {
            return new Response(JSON.stringify({ error: 'OpenAI API key not configured.' }), {
                status: 500,
                headers: { 'Content-Type': 'application/json' },
            });
        }

        try {
            const body = await request.json();
            
            const response = await fetch('https://api.openai.com/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${openaiApiKey}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    model: model,
                    ...body,
                }),
            });

            const data = await response.json();
            
            return new Response(JSON.stringify(data), {
                status: response.status,
                headers: { 
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
            });
        } catch (error) {
            return new Response(JSON.stringify({ error: 'Internal server error', message: error.message }), {
                status: 500,
                headers: { 'Content-Type': 'application/json' },
            });
        }
    }

    return new Response('Not Found', { status: 404 });
}

addEventListener('fetch', (event) => {
    event.respondWith(handleFetch(event.request));
});