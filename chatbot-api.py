#!/usr/bin/env python3
"""
SpectroScience AI Chatbot Backend
OpenAI-powered NIR Spectroscopy Teaching Assistant
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import openai
import os
import json
import uuid
from datetime import datetime
import boto3
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend access

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_S3_BUCKET = os.getenv('AWS_S3_BUCKET', 'clovitek')

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# System prompt for NIR Spectroscopy Teaching Assistant
SYSTEM_PROMPT = """You are SpectroScience AI, an expert NIR (Near-Infrared) Spectroscopy Teaching Assistant.

Your role is to help students learn NIR spectroscopy concepts through:
- Clear explanations of NIR principles and techniques
- Step-by-step problem solving for calculations
- Guidance on spectral interpretation
- Practical applications in various industries
- Chemometrics and data analysis methods

Key topics you cover:
- Beer's Law and quantitative analysis
- Wavelength selection and spectral preprocessing
- Calibration model development (PLS, PCR)
- Signal-to-noise ratio and instrument quality
- Moisture, protein, fat analysis
- PCA and multivariate analysis
- ROI calculations for NIR systems

Teaching style:
- Patient and encouraging
- Use examples and analogies
- Break down complex concepts
- Provide step-by-step solutions
- Reference course materials when relevant

When students ask questions:
1. Understand their level and adapt explanations
2. Use proper terminology but explain it
3. Show calculations with clear steps
4. Provide practical examples
5. Encourage further exploration

Keep responses concise (95-125 words for education mode) unless detailed explanation is needed."""

# In-memory conversation storage (use Redis/database in production)
conversations = {}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'SpectroScience AI Chatbot',
        'version': '1.0.0'
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat endpoint for OpenAI-powered conversations
    
    Request body:
    {
        "message": "User's question",
        "conversation_id": "optional-conversation-id",
        "context": {
            "course_week": 3,
            "lesson_id": "nir-fundamentals-week3"
        }
    }
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id') or str(uuid.uuid4())
        context = data.get('context', {})
        
        if not message:
            return jsonify({
                'success': False,
                'error': 'Message is required'
            }), 400
        
        # Get or create conversation history
        if conversation_id not in conversations:
            conversations[conversation_id] = {
                'messages': [],
                'created_at': datetime.now().isoformat(),
                'context': context
            }
        
        conversation = conversations[conversation_id]
        
        # Build messages for OpenAI
        messages = [
            {'role': 'system', 'content': SYSTEM_PROMPT}
        ]
        
        # Add conversation history (last 10 messages to manage token usage)
        messages.extend(conversation['messages'][-10:])
        
        # Add current user message
        messages.append({'role': 'user', 'content': message})
        
        # Call OpenAI API
        response = openai.ChatCompletion.create(
            model='gpt-4',  # Use gpt-3.5-turbo for faster/cheaper responses
            messages=messages,
            temperature=0.7,
            max_tokens=500,
            top_p=0.9,
            frequency_penalty=0.3,
            presence_penalty=0.3
        )
        
        # Extract assistant's response
        assistant_message = response.choices[0].message.content
        
        # Update conversation history
        conversation['messages'].append({'role': 'user', 'content': message})
        conversation['messages'].append({'role': 'assistant', 'content': assistant_message})
        conversation['updated_at'] = datetime.now().isoformat()
        
        return jsonify({
            'success': True,
            'response': assistant_message,
            'conversation_id': conversation_id,
            'metadata': {
                'model': response.model,
                'tokens_used': response.usage.total_tokens,
                'finish_reason': response.choices[0].finish_reason
            }
        })
        
    except openai.error.AuthenticationError:
        return jsonify({
            'success': False,
            'error': 'OpenAI API authentication failed. Check API key.'
        }), 500
        
    except openai.error.RateLimitError:
        return jsonify({
            'success': False,
            'error': 'Rate limit exceeded. Please try again in a moment.'
        }), 429
        
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """
    File upload endpoint with S3 storage
    
    Handles file uploads from chatbot (assignments, spectra, etc.)
    Stores files in S3 bucket under users/vitaly/chatbot-uploads/
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file provided'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # Get additional metadata
        conversation_id = request.form.get('conversation_id', 'unknown')
        file_type = request.form.get('file_type', 'general')
        
        # Secure filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}_{filename}"
        
        # S3 path: users/vitaly/chatbot-uploads/YYYYMMDD/filename
        date_folder = datetime.now().strftime('%Y%m%d')
        s3_key = f"users/vitaly/chatbot-uploads/{date_folder}/{unique_filename}"
        
        # Upload to S3
        s3_client.upload_fileobj(
            file,
            AWS_S3_BUCKET,
            s3_key,
            ExtraArgs={
                'ContentType': file.content_type,
                'Metadata': {
                    'conversation_id': conversation_id,
                    'file_type': file_type,
                    'original_filename': filename,
                    'upload_timestamp': datetime.now().isoformat()
                }
            }
        )
        
        # Generate S3 URL
        s3_url = f"s3://{AWS_S3_BUCKET}/{s3_key}"
        
        # Generate presigned URL for temporary access (7 days)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': AWS_S3_BUCKET, 'Key': s3_key},
            ExpiresIn=604800  # 7 days
        )
        
        return jsonify({
            'success': True,
            'file': {
                'filename': filename,
                'unique_filename': unique_filename,
                's3_key': s3_key,
                's3_url': s3_url,
                'presigned_url': presigned_url,
                'size': file.content_length,
                'content_type': file.content_type,
                'uploaded_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        print(f"Error in upload endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Upload failed: {str(e)}'
        }), 500

@app.route('/api/grade', methods=['POST'])
def grade_assignment():
    """
    AI-powered assignment grading
    
    Request body:
    {
        "assignment_id": "week3-quiz-1",
        "student_id": "student-12345",
        "answers": [
            {
                "question_id": "q1",
                "question": "Explain Beer's Law",
                "answer": "Student's answer..."
            }
        ]
    }
    """
    try:
        data = request.json
        assignment_id = data.get('assignment_id')
        answers = data.get('answers', [])
        
        if not answers:
            return jsonify({
                'success': False,
                'error': 'No answers provided'
            }), 400
        
        grading_results = []
        total_score = 0
        max_score = 0
        
        for answer_data in answers:
            question = answer_data.get('question', '')
            answer = answer_data.get('answer', '')
            question_id = answer_data.get('question_id', '')
            
            # Build grading prompt
            grading_prompt = f"""As an NIR spectroscopy instructor, grade this student's answer.

Question: {question}

Student's Answer: {answer}

Provide:
1. Score out of 20 points
2. Brief feedback (2-3 sentences)
3. What they did well
4. What needs improvement

Format your response as JSON:
{{
    "score": <number 0-20>,
    "feedback": "<feedback text>",
    "strengths": ["<strength 1>", "<strength 2>"],
    "improvements": ["<improvement 1>", "<improvement 2>"]
}}"""
            
            # Call OpenAI for grading
            response = openai.ChatCompletion.create(
                model='gpt-4',
                messages=[
                    {'role': 'system', 'content': 'You are an expert NIR spectroscopy instructor grading student assignments.'},
                    {'role': 'user', 'content': grading_prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            # Parse grading result
            try:
                grading_result = json.loads(response.choices[0].message.content)
            except:
                # Fallback if JSON parsing fails
                grading_result = {
                    'score': 15,
                    'feedback': response.choices[0].message.content,
                    'strengths': ['Answer provided'],
                    'improvements': ['Could be more detailed']
                }
            
            score = grading_result.get('score', 0)
            total_score += score
            max_score += 20
            
            grading_results.append({
                'question_id': question_id,
                'score': score,
                'max_score': 20,
                'feedback': grading_result.get('feedback', ''),
                'strengths': grading_result.get('strengths', []),
                'improvements': grading_result.get('improvements', [])
            })
        
        # Calculate overall grade
        percentage = (total_score / max_score * 100) if max_score > 0 else 0
        
        if percentage >= 90:
            letter_grade = 'A'
        elif percentage >= 80:
            letter_grade = 'B'
        elif percentage >= 70:
            letter_grade = 'C'
        elif percentage >= 60:
            letter_grade = 'D'
        else:
            letter_grade = 'F'
        
        return jsonify({
            'success': True,
            'assignment_id': assignment_id,
            'overall_score': total_score,
            'max_score': max_score,
            'percentage': round(percentage, 1),
            'grade': letter_grade,
            'results': grading_results,
            'overall_feedback': f"You scored {total_score}/{max_score} ({percentage:.1f}%). {'Excellent work!' if percentage >= 80 else 'Keep practicing!'}"
        })
        
    except Exception as e:
        print(f"Error in grade endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Grading failed: {str(e)}'
        }), 500

@app.route('/api/conversations/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    """Get conversation history"""
    if conversation_id in conversations:
        return jsonify({
            'success': True,
            'conversation': conversations[conversation_id]
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Conversation not found'
        }), 404

if __name__ == '__main__':
    # Check required environment variables
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY environment variable is required")
        exit(1)
    
    if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        print("WARNING: AWS credentials not found. File upload will not work.")
    
    print("=" * 60)
    print("SpectroScience AI Chatbot Backend Starting...")
    print("=" * 60)
    print(f"OpenAI API Key: {'✅ Configured' if OPENAI_API_KEY else '❌ Missing'}")
    print(f"AWS S3 Bucket: {AWS_S3_BUCKET}")
    print(f"AWS Region: {AWS_REGION}")
    print("=" * 60)
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5001, debug=False)
