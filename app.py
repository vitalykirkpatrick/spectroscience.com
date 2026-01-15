#!/usr/bin/env python3
"""
SpectroScience AI - Chatbot Backend
OpenAI-powered NIR Spectroscopy Teaching Assistant
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import boto3
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuration
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
S3_BUCKET = 'clovitek'
S3_BASE_PATH = 'users/vitaly@clovitek.com/chatbot-uploads/'

# Initialize clients
openai.api_key = OPENAI_API_KEY
s3 = boto3.client('s3')

# Load NIR course knowledge base
KNOWLEDGE_BASE_FILE = '/var/www/app.clovitek.com/spectro-backend/nir_knowledge_base.json'
knowledge_base = []

try:
    with open(KNOWLEDGE_BASE_FILE, 'r') as f:
        knowledge_base = json.load(f)
    print(f"✅ Loaded {len(knowledge_base)} lessons from knowledge base")
except Exception as e:
    print(f"⚠️  Could not load knowledge base: {e}")

# System prompt with course knowledge
SYSTEM_PROMPT = """You are SpectroScience AI, an expert NIR (Near-Infrared) Spectroscopy teaching assistant.

You have access to a comprehensive NIR Essentials Course covering all aspects of near-infrared spectroscopy, from fundamental concepts to advanced applications in agriculture, pharmaceuticals, and industry.

Your role is to:
1. Answer questions about NIR spectroscopy concepts, theory, and applications naturally
2. Draw from course materials when relevant, but present information conversationally
3. Explain complex topics in clear, educational language suitable for students
4. Provide practical examples and real-world applications
5. Reference videos, slides, and documents from the course when they help illustrate concepts
6. Generate helpful visualizations and calculations when requested

IMPORTANT:
- Answer questions naturally without explicitly mentioning "Week X" or "Lesson Y" unless specifically asked
- When referencing course materials, say things like "In the course materials on calibration..." or "As covered in the fundamentals section..."
- If a video or document is relevant, mention it naturally: "There's a helpful video that demonstrates this concept" and provide the link
- Focus on teaching the concept, not the course structure
- Be encouraging, patient, and thorough in your explanations
- Always provide CDN links to media files when referencing them
"""

def search_knowledge_base(query):
    """Smart keyword search in knowledge base with video/document detection"""
    results = []
    query_lower = query.lower()
    
    # Keywords for different topics
    topic_keywords = {
        'calibration': ['calibration', 'model', 'prediction', 'accuracy'],
        'instrumentation': ['instrument', 'spectrometer', 'detector', 'hardware'],
        'applications': ['application', 'agriculture', 'pharmaceutical', 'food', 'industry'],
        'theory': ['theory', 'wavelength', 'absorption', 'light', 'molecular'],
        'data': ['data', 'analysis', 'chemometrics', 'statistics']
    }
    
    for entry in knowledge_base:
        score = 0
        
        # Direct keyword match in lesson name
        if any(word in entry['lesson_name'].lower() for word in query_lower.split()):
            score += 10
        
        # Topic relevance
        for topic, keywords in topic_keywords.items():
            if any(kw in query_lower for kw in keywords):
                if any(kw in entry['lesson_name'].lower() for kw in keywords):
                    score += 5
        
        # Boost if has videos (more engaging)
        if entry.get('videos'):
            score += 2
        
        # Boost if has documents (more detailed)
        if entry.get('documents'):
            score += 1
        
        if score > 0:
            entry['relevance_score'] = score
            results.append(entry)
    
    # Sort by relevance
    results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
    
    return results[:3]  # Return top 3 matches

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'knowledge_base_loaded': len(knowledge_base) > 0,
        'total_lessons': len(knowledge_base)
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Chat endpoint with NIR course knowledge"""
    try:
        data = request.json
        user_message = data.get('message', '')
        conversation_history = data.get('history', [])
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Search knowledge base for relevant content
        relevant_lessons = search_knowledge_base(user_message)
        
        # Build context from knowledge base
        context = ""
        media_references = []
        
        if relevant_lessons:
            context = "\n\nRelevant course materials you can reference:\n"
            for lesson in relevant_lessons:
                context += f"\n- Topic: {lesson['lesson_name']}"
                
                # Add video references
                if lesson.get('videos'):
                    context += f"\n  Videos available ({len(lesson['videos'])}):"  
                    for video in lesson['videos']:
                        context += f"\n    - {video['filename']}: {video['cdn_url']}"
                        media_references.append({
                            'type': 'video',
                            'title': video['filename'],
                            'url': video['cdn_url']
                        })
                
                # Add document references
                if lesson.get('documents'):
                    context += f"\n  Documents available ({len(lesson['documents'])}):"  
                    for doc in lesson['documents']:
                        context += f"\n    - {doc['filename']}: {doc['cdn_url']}"
                        media_references.append({
                            'type': 'document',
                            'title': doc['filename'],
                            'url': doc['cdn_url']
                        })
                
                # Add slide references
                if lesson.get('slides'):
                    context += f"\n  Slides: {lesson['slide_count']} available at {lesson.get('cdn_base', '')}"
        
        # Build messages for OpenAI
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + context}
        ]
        
        # Add conversation history
        for msg in conversation_history[-10:]:  # Last 10 messages
            messages.append({
                "role": msg.get('role', 'user'),
                "content": msg.get('content', '')
            })
        
        # Add current message
        messages.append({"role": "user", "content": user_message})
        
        # Call OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        assistant_message = response.choices[0].message.content
        
        return jsonify({
            'response': assistant_message,
            'media_references': media_references,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload():
    """Upload file to S3"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Generate S3 key
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        s3_key = f"{S3_BASE_PATH}{timestamp}_{file.filename}"
        
        # Upload to S3
        s3.upload_fileobj(
            file,
            S3_BUCKET,
            s3_key,
            ExtraArgs={'ContentType': file.content_type}
        )
        
        s3_url = f"s3://{S3_BUCKET}/{s3_key}"
        
        return jsonify({
            'success': True,
            's3_url': s3_url,
            's3_key': s3_key,
            'filename': file.filename
        })
        
    except Exception as e:
        print(f"Error in upload endpoint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/course', methods=['GET'])
def get_course_structure():
    """Get course structure"""
    try:
        # Organize by week
        weeks = {}
        for entry in knowledge_base:
            week = entry['week']
            if week not in weeks:
                weeks[week] = {
                    'week_num': entry['week_num'],
                    'lessons': []
                }
            weeks[week]['lessons'].append({
                'lesson_id': entry['lesson_id'],
                'lesson_name': entry['lesson_name'],
                'slide_count': entry['slide_count'],
                's3_path': entry['s3_path']
            })
        
        return jsonify({
            'total_weeks': len(weeks),
            'total_lessons': len(knowledge_base),
            'weeks': weeks
        })
        
    except Exception as e:
        print(f"Error in course endpoint: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 80)
    print("🚀 SpectroScience AI Backend Starting...")
    print("=" * 80)
    print(f"📚 Knowledge Base: {len(knowledge_base)} lessons loaded")
    print(f"🔑 OpenAI API Key: {'✅ Set' if OPENAI_API_KEY else '❌ Not set'}")
    print("=" * 80)
    app.run(host='0.0.0.0', port=5000, debug=False)
