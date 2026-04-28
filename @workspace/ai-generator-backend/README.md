# Ollama AI Chat Generator

A Flask-based chat interface that connects to a local Ollama instance for AI-powered conversations.

## Prerequisites

1. **Ollama** must be installed and running on your local machine:
   - Download from: https://ollama.ai
   - Start Ollama: `ollama serve`
   - Pull a model: `ollama pull llama2` (or your preferred model)

2. **Python 3.8+** with required dependencies

## Installation

```bash
cd ai-generator-backend
pip install -r requirements.txt
```

## Usage

### 1. Start Ollama

```bash
ollama serve
```

Then pull a model (if not already installed):

```bash
ollama pull llama2
# Or try: ollama pull mistral, ollama pull codellama
```

### 2. Start the Flask Server

```bash
python app.py
```

The server will start at `http://localhost:5000`

### 3. Access the Chat Interface

Open your browser and navigate to: `http://localhost:5000`

## Features

- ✅ Multiple model support (select from available Ollama models)
- ✅ Multi-chat sessions with unique chat IDs
- ✅ Start, clear, and delete chat sessions
- ✅ Real-time chat interface with typing indicators
- ✅ Status indicator showing Ollama connection health
- ✅ Conversational memory (context-aware responses)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Check Ollama status and get available models |
| `/api/models` | GET | Get list of available Ollama models |
| `/api/chat/start` | POST | Start a new chat session |
| `/api/chat/message` | POST | Send a message and get AI response |
| `/api/chat/delete` | POST | Delete a chat session |
| `/api/chat/clear` | POST | Clear messages in current chat |

## Environment Variables

Optional configuration:

```bash
OLLAMA_BASE_URL=http://localhost:11434  # Change if using custom Ollama port
FLASK_ENV=development                    # Flask environment
```

## Default Configuration

- **Flask Server**: `http://localhost:5000`
- **Ollama Endpoint**: `http://localhost:11434`
- **Port**: `5000` (Flask), `11434` (Ollama)

## Troubleshooting

### Ollama not running
Make sure Ollama is running with `ollama serve`. Check status with:
```bash
curl http://localhost:11434/api/tags
```

### No models available
Pull a model:
```bash
ollama pull llama2
```

### Port already in use
Change the port in `app.py`:
```python
app.run(host='0.0.0.0', port=5001, debug=True)
```

## License

MIT License