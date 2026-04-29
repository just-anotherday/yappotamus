require('dotenv').config();

const config = {
    openai: {
        apiKey: process.env.OPENAI_API_KEY || '',
        model: 'gpt-3.5-turbo'
    },
    port: process.env.PORT || 3001
};

module.exports = config;