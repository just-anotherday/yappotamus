from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json

app = Flask(__name__)
CORS(app)

# Ollama local endpoint
OLLAMA_BASE_URL = "http://localhost:11434"

# Store chats in memory (in production, use a database)
chats = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def health():
    """Check if Ollama is running"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            return jsonify({"status": "ok", "models": response.json()})
    except Exception as e:
        pass
    return jsonify({"status": "offline", "error": "Ollama is not running"}), 503

@app.route('/api/models', methods=['GET'])
def get_models():
    """Get available Ollama models"""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        if response.status_code == 200:
            models = response.json().get('models', [])
            return jsonify({
                "models": [m['name'] for m in models],
                "default": models[0]['name'] if models else None
            })
    except Exception as e:
        pass
    return jsonify({"error": "Failed to fetch models"}), 500

@app.route('/api/chat/start', methods=['POST'])
def start_chat():
    """Start a new chat session"""
    data = request.json
    chat_id = data.get('chatId', 'session_1')
    model = data.get('model', 'llama2')  # Default model if not specified
    
    # Save chat session info
    chats[chat_id] = {
        'model': model,
        'messages': []
    }
    
    return jsonify({
        "status": "ok",
        "chatId": chat_id,
        "model": model
    })

@app.route('/api/chat/message', methods=['POST'])
def send_message():
    """Send a message and get response from Ollama"""
    data = request.json
    chat_id = data.get('chatId', 'session_1')
    user_message = data.get('message', '')
    
    if not chat_id or not user_message:
        return jsonify({"error": "Missing chatId or message"}), 400
    
    chat_session = chats.get(chat_id)
    if not chat_session:
        return jsonify({"error": "Chat not found"}), 404
    
    model = chat_session['model']
    
    # Store user message
    chat_session['messages'].append({
        'role': 'user',
        'content': user_message
    })
    
    try:
        # Get response from Ollama
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": chat_session['messages'],
                "stream": False
            },
            timeout=120
        )
        
        if response.status_code == 200:
            ai_response = response.json().get('message', {}).get('content', '')
            
            # Store AI response
            chat_session['messages'].append({
                'role': 'assistant',
                'content': ai_response
            })
            
            return jsonify({
                "status": "ok",
                "response": ai_response
            })
        else:
            return jsonify({
                "error": f"Ollama request failed: {response.status_code}"
            }), response.status_code
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/chat/delete', methods=['POST'])
def delete_chat():
    """Delete a chat session"""
    data = request.json
    chat_id = data.get('chatId', '')
    
    if chat_id and chat_id in chats:
        deleted_chat = chats.pop(chat_id)
        return jsonify({
            "status": "deleted",
            "chatId": chat_id,
            "messages_cleared": len(deleted_chat['messages'])
        })
    else:
        return jsonify({
            "status": "not_found",
            "message": "Chat not found"
        })

@app.route('/api/chat/clear', methods=['POST'])
def clear_messages():
    """Clear messages in current chat"""
    chat_id = request.args.get('chatId', 'session_1')
    
    if chat_id in chats:
        chats[chat_id]['messages'] = []
        return jsonify({
            "status": "ok",
            "chatId": chat_id,
            "message": "Messages cleared"
        })
    
    return jsonify({
        "status": "not_found",
        "chatId": chat_id
    }), 404

if __name__ == '__main__':
    print("=" * 50)
    print("Ollama Chat Server Starting...")
    print("=" * 50)
    print(f"Ollama endpoint: {OLLAMA_BASE_URL}")
    print("Server running at: http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)