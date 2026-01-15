#!/usr/bin/env python3
"""
Auto-Sync Course Updates Script
Monitors S3 for course changes, detects videos, updates knowledge base
"""

import boto3
import json
import os
from datetime import datetime
from pathlib import Path

# Configuration
S3_BUCKET = 'clovitek'
S3_COURSE_PATH = 'users/vitaly@clovitek.com/courses/NIR_Essentials_Course/'
CDN_BASE_URL = 'https://cdn.clovitek.com'
KNOWLEDGE_BASE_FILE = '/var/www/app.clovitek.com/spectro-backend/nir_knowledge_base.json'
TRAINING_LOG_FILE = '/var/www/app.clovitek.com/spectro-backend/training_log.json'

# Initialize S3 client
s3 = boto3.client('s3')

# Video file extensions
VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.avi', '.mkv']
IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
DOCUMENT_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.txt', '.md']

def scan_course_structure():
    """Scan S3 for complete course structure including videos"""
    print("🔍 Scanning S3 course structure...")
    
    lessons = []
    
    try:
        # List all objects in course path
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_COURSE_PATH)
        
        current_lesson = None
        
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                relative_path = key.replace(S3_COURSE_PATH, '')
                
                # Skip if not in a Week folder
                if not relative_path.startswith('Week_'):
                    continue
                
                parts = relative_path.split('/')
                if len(parts) < 2:
                    continue
                
                week_folder = parts[0]  # e.g., "Week_01"
                week_num = int(week_folder.split('_')[1])
                
                # Check if this is a lesson folder
                if len(parts) >= 2 and parts[1].startswith('L'):
                    lesson_folder = parts[1]
                    lesson_id = lesson_folder
                    
                    # Create or update lesson entry
                    lesson_key = f"{week_folder}/{lesson_folder}"
                    
                    if current_lesson is None or current_lesson['lesson_key'] != lesson_key:
                        # Save previous lesson if exists
                        if current_lesson:
                            lessons.append(current_lesson)
                        
                        # Start new lesson
                        current_lesson = {
                            'lesson_key': lesson_key,
                            'week': week_folder,
                            'week_num': week_num,
                            'lesson_id': lesson_id,
                            'lesson_name': lesson_folder.replace('_', ' '),
                            's3_path': f"s3://{S3_BUCKET}/{S3_COURSE_PATH}{lesson_key}/",
                            'cdn_base': f"{CDN_BASE_URL}/{S3_COURSE_PATH}{lesson_key}/",
                            'slide_count': 0,
                            'slides': [],
                            'videos': [],
                            'documents': [],
                            'last_modified': obj['LastModified'].isoformat()
                        }
                    
                    # Categorize file
                    if len(parts) >= 3:
                        filename = parts[2]
                        file_ext = Path(filename).suffix.lower()
                        cdn_url = f"{CDN_BASE_URL}/{key}"
                        
                        if file_ext in VIDEO_EXTENSIONS:
                            current_lesson['videos'].append({
                                'filename': filename,
                                'cdn_url': cdn_url,
                                's3_key': key,
                                'size': obj['Size'],
                                'last_modified': obj['LastModified'].isoformat()
                            })
                        elif file_ext in IMAGE_EXTENSIONS:
                            current_lesson['slides'].append({
                                'filename': filename,
                                'cdn_url': cdn_url,
                                's3_key': key
                            })
                            current_lesson['slide_count'] += 1
                        elif file_ext in DOCUMENT_EXTENSIONS:
                            current_lesson['documents'].append({
                                'filename': filename,
                                'cdn_url': cdn_url,
                                's3_key': key,
                                'type': file_ext[1:]  # Remove dot
                            })
        
        # Don't forget the last lesson
        if current_lesson:
            lessons.append(current_lesson)
        
        print(f"✅ Found {len(lessons)} lessons")
        return lessons
        
    except Exception as e:
        print(f"❌ Error scanning course: {e}")
        return []

def save_knowledge_base(lessons):
    """Save updated knowledge base"""
    try:
        # Create backup
        if os.path.exists(KNOWLEDGE_BASE_FILE):
            backup_file = f"{KNOWLEDGE_BASE_FILE}.backup"
            os.rename(KNOWLEDGE_BASE_FILE, backup_file)
            print(f"📦 Backed up existing knowledge base")
        
        # Save new knowledge base
        with open(KNOWLEDGE_BASE_FILE, 'w') as f:
            json.dump(lessons, f, indent=2)
        
        print(f"✅ Knowledge base updated: {len(lessons)} lessons")
        
        # Save training log
        training_log = {
            'last_sync': datetime.now().isoformat(),
            'total_lessons': len(lessons),
            'total_videos': sum(len(l.get('videos', [])) for l in lessons),
            'total_slides': sum(l['slide_count'] for l in lessons),
            'total_documents': sum(len(l.get('documents', [])) for l in lessons),
            'weeks': {}
        }
        
        for lesson in lessons:
            week = lesson['week']
            if week not in training_log['weeks']:
                training_log['weeks'][week] = {
                    'lesson_count': 0,
                    'video_count': 0,
                    'slide_count': 0
                }
            training_log['weeks'][week]['lesson_count'] += 1
            training_log['weeks'][week]['video_count'] += len(lesson.get('videos', []))
            training_log['weeks'][week]['slide_count'] += lesson['slide_count']
        
        with open(TRAINING_LOG_FILE, 'w') as f:
            json.dump(training_log, f, indent=2)
        
        print(f"✅ Training log updated")
        return True
        
    except Exception as e:
        print(f"❌ Error saving knowledge base: {e}")
        return False

def restart_backend():
    """Restart backend to load new knowledge base"""
    try:
        import subprocess
        result = subprocess.run(['pm2', 'restart', 'spectro-backend'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Backend restarted successfully")
            return True
        else:
            print(f"⚠️  Backend restart failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️  Could not restart backend: {e}")
        return False

def main():
    print("=" * 80)
    print("🔄 NIR Course Auto-Sync")
    print("=" * 80)
    print()
    
    # Scan course
    lessons = scan_course_structure()
    
    if not lessons:
        print("❌ No lessons found")
        return 1
    
    # Save knowledge base
    if not save_knowledge_base(lessons):
        return 1
    
    # Restart backend
    restart_backend()
    
    print()
    print("=" * 80)
    print("✅ SYNC COMPLETE!")
    print("=" * 80)
    print(f"📚 Total Lessons: {len(lessons)}")
    print(f"🎥 Total Videos: {sum(len(l.get('videos', [])) for l in lessons)}")
    print(f"📊 Total Slides: {sum(l['slide_count'] for l in lessons)}")
    print(f"📄 Total Documents: {sum(len(l.get('documents', [])) for l in lessons)}")
    print("=" * 80)
    
    return 0

if __name__ == '__main__':
    exit(main())
