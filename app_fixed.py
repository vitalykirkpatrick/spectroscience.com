from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)

# Load knowledge base
knowledge_base = []
kb_path = '/var/www/app.clovitek.com/spectro-backend/nir_knowledge_base.json'
if os.path.exists(kb_path):
    with open(kb_path, 'r') as f:
        knowledge_base = json.load(f)
    print(f"✅ Loaded {len(knowledge_base)} lessons from knowledge base")
else:
    print("⚠️  Knowledge base not found")

# Initialize OpenAI
client = None
if os.getenv('OPENAI_API_KEY'):
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    print("✅ OpenAI client initialized")
else:
    print("⚠️  OPENAI_API_KEY not set")

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        "success": True,
        "message": "SpectroScience AI Backend",
        "version": "1.0.0",
        "lessons": len(knowledge_base)
    })

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        "success": True,
        "status": "healthy",
        "lessons": len(knowledge_base),
        "openai": client is not None
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        message = data.get('message', '')
        
        if not client:
            return jsonify({
                "success": False,
                "error": "OpenAI API not configured"
            }), 500
        
        # Build context from knowledge base
        context = f"You are a NIR spectroscopy teaching assistant. You have access to course materials covering {len(knowledge_base)} lessons across 8 weeks.\n\n"
        context += "Answer naturally without mentioning 'Week X' or 'Lesson Y' unless specifically asked.\n\n"
        
        # Add relevant lessons to context (simple keyword matching)
        relevant_lessons = []
        keywords = message.lower().split()
        for lesson in knowledge_base[:5]:  # Limit to first 5 for now
            lesson_text = f"{lesson.get('lesson_name', '')} {lesson.get('week_name', '')}".lower()
            if any(kw in lesson_text for kw in keywords):
                relevant_lessons.append(lesson)
        
        if relevant_lessons:
            context += "Relevant course materials:\n"
            for lesson in relevant_lessons:
                context += f"- {lesson.get('lesson_name', 'Unknown')}: {lesson.get('slide_count', 0)} slides\n"
        
        # Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": context},
                {"role": "user", "content": message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content
        
        return jsonify({
            "success": True,
            "response": answer,
            "sources": [l.get('lesson_name') for l in relevant_lessons]
        })
        
    except Exception as e:
        print(f"❌ Chat error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/course', methods=['GET'])
def get_course():
    return jsonify({
        "success": True,
        "lessons": knowledge_base
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    print("=" * 80)
    print("🚀 SpectroScience AI Backend Starting...")
    print("=" * 80)
    print(f"📚 Knowledge Base: {len(knowledge_base)} lessons loaded")
    print(f"🔑 OpenAI API Key: {'✅ Set' if os.getenv('OPENAI_API_KEY') else '❌ Not set'}")
    print(f"🌐 Port: {port}")
    print("=" * 80)
    app.run(host='0.0.0.0', port=port, debug=False)
