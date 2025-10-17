// server.js
import express from 'express';
import fetch from 'node-fetch';
import cors from 'cors';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

// Ensure images folder exists
const imagesDir = path.join(process.cwd(), 'images');
if (!fs.existsSync(imagesDir)) fs.mkdirSync(imagesDir);
app.use('/images', express.static(imagesDir));

const MAX_PROMPT_LENGTH = 200;      // Limit prompt size
const MAX_REQUESTS_PER_MIN = 20;    // Simple rate limit
let requestCount = 0;
setInterval(() => { requestCount = 0; }, 60_000);

app.post('/ai', async (req, res) => {
  if (requestCount >= MAX_REQUESTS_PER_MIN) {
    return res.status(429).json({ error: "Too many requests. Try again later." });
  }
  requestCount++;

  const { prompt, type } = req.body;
  if (!prompt || prompt.length > MAX_PROMPT_LENGTH) {
    return res.status(400).json({ error: "Invalid prompt." });
  }

  try {
    let result;

    // Mock mode for testing
    if (process.env.MOCK_API === "true") {
      result = type === "image"
        ? "https://via.placeholder.com/512"
        : `Mock response for: "${prompt}"`;
    } else if (type === "image") {
      // OpenAI image generation
      const response = await fetch('https://api.openai.com/v1/images/generations', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ prompt, n: 1, size: "512x512" })
      });

      const data = await response.json();
      const imageUrl = data.data?.[0]?.url;
      if (!imageUrl) throw new Error("No image returned from OpenAI");

      // Download and save image locally
      const imgRes = await fetch(imageUrl);
      const buffer = await imgRes.buffer();
      const fileName = `${Date.now()}.png`;
      const filePath = path.join(imagesDir, fileName);
      fs.writeFileSync(filePath, buffer);

      result = `/images/${fileName}`;
    } else {
      // OpenAI text completion
      const response = await fetch('https://api.openai.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: "gpt-3.5-turbo",
          messages: [{ role: "user", content: prompt }],
          max_tokens: 150
        })
      });

      const data = await response.json();
      console.log("OpenAI full response:", data); // Debugging
      result = data.choices?.[0]?.message?.content || "No text returned";
    }

    res.json({ result });

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "AI request failed", details: err.message });
  }
});

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => console.log(`AI backend running on port ${PORT}`));
