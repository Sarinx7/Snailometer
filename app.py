from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit
import cv2
import math
import time
import os
import base64
import numpy as np
from werkzeug.utils import secure_filename
import threading
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'snailometer_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  

from flask_cors import CORS
CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='eventlet',
                    logger=True, 
                    engineio_logger=True)

unit_mode = "pixels"
PIXEL_TO_MM = 0.2646
webcam_active = False
video_cap = None

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

import os
import cv2
import numpy as np
import datetime
import base64
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import time
import eventlet
import io
import sys

def calculate_speed_and_distance(positions):
    """Calculate total distance and average speed from position history"""
    if len(positions) < 2:
        return 0, 0

    total_distance = 0
    if len(positions) <= 10:
        for i in range(1, len(positions)):
            x1, y1, _ = positions[i - 1]
            x2, y2, _ = positions[i]
            dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            total_distance += dist
    else:
        sample_points = positions[::2]  # Take every 2nd point
        for i in range(1, len(sample_points)):
            x1, y1, _ = sample_points[i - 1]
            x2, y2, _ = sample_points[i]
            dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            total_distance += dist
        total_distance *= 2

    total_time = positions[-1][2] - positions[0][2]
    avg_speed = total_distance / total_time if total_time > 0 else 0

    return total_distance, avg_speed

def convert_units(value):
    return value * PIXEL_TO_MM if unit_mode == "mm" else value

def process_frame(frame, positions):
    current_time = time.time()
    display_frame = None
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    
    _, thresh = cv2.threshold(gray, 90, 255, cv2.THRESH_BINARY_INV)
    
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    speed = 0
    tracking_data = {
        'speed': 0,
        'total_distance': 0,
        'avg_speed': 0,
        'unit': unit_mode,
        'detected': False
    }

    if contours:
        min_area = 100
        max_area = frame.shape[0] * frame.shape[1] * 0.5
        snail_candidates = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = max(w / h, h / w) if h > 0 and w > 0 else 0
            # Snails are usually elongated, not round. Accept aspect ratios between 1.2 and 4.0
            if 1.2 <= aspect_ratio <= 4.0:
                # Optional: add color filtering here if needed
                snail_candidates.append((c, area, x, y, w, h))
        if snail_candidates:
            # Pick the largest snail-like contour
            snail_candidates.sort(key=lambda tup: tup[1], reverse=True)
            c, area, x, y, w, h = snail_candidates[0]
            display_frame = frame.copy()
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                positions.append((cx, cy, current_time))
                if len(positions) > 30:
                    positions.pop(0)
                if len(positions) >= 2:
                    x1, y1, t1 = positions[-2]
                    x2, y2, t2 = positions[-1]
                    dt = t2 - t1
                    dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    if dt > 0:
                        speed = dist / dt
                speed_converted = convert_units(speed)
                dist_total, avg_speed = calculate_speed_and_distance(positions)
                dist_converted = convert_units(dist_total)
                avg_speed_converted = convert_units(avg_speed)
                color = (0, 255, 0)
                thickness = 2
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, thickness)
                unit_text = "px/s" if unit_mode == "pixels" else "mm/s"
                speed_text = f"Snail: {round(speed_converted, 1)} {unit_text}"
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                text_thickness = 1
                text_color = (0, 255, 0)
                text_x = x
                text_y = y - 10 if y > 30 else y + h + 20
                cv2.rectangle(display_frame, (text_x - 2, text_y - 15), (text_x + len(speed_text) * 11, text_y + 2), (0, 0, 0), -1)
                cv2.putText(display_frame, speed_text, (text_x, text_y), font, font_scale, text_color, text_thickness)
                tracking_data = {
                    'speed': round(speed_converted, 2),
                    'total_distance': round(dist_converted, 2),
                    'avg_speed': round(avg_speed_converted, 2),
                    'unit': unit_mode,
                    'detected': True,
                    'position': {'x': cx, 'y': cy},
                    'bounding_box': {'x': x, 'y': y, 'w': w, 'h': h}
                }
    
    if display_frame is None:
        display_frame = frame.copy()
        
    return tracking_data, display_frame

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_video', methods=['POST'])
def upload_video():
    
    if 'video' not in request.files:
        app.logger.error("No video file in request")
        return jsonify({'error': 'No video file provided'}), 400
    
    file = request.files['video']
    app.logger.info(f"File name: {file.filename}")
    app.logger.info(f"File content type: {file.content_type}")
    
    if file.filename == '':
        app.logger.error("Empty filename")
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            app.logger.info(f"File saved to {filepath}")
            
            threading.Thread(target=process_uploaded_video, args=(filepath,)).start()
            
            return jsonify({'message': 'Video uploaded successfully', 'filename': filename})
        except Exception as e:
            app.logger.error(f"Error saving file: {str(e)}")
            return jsonify({'error': f'Error uploading file: {str(e)}'}), 500

def process_uploaded_video(filepath):
    app.logger.info(f"Starting to process video: {filepath}")
    
    try:
        cap = cv2.VideoCapture(filepath)
        if not cap.isOpened():
            app.logger.error(f"Could not open video file: {filepath}")
            socketio.emit('video_error', {'error': 'Could not open video file'})
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        app.logger.info(f"Video opened successfully: {fps} FPS, {total_frames} frames")
        
        skip_frames = 6          
        if total_frames > 1000:
            skip_frames = 5
        elif total_frames < 300:
            skip_frames = 1 
            
        app.logger.info(f"Processing every {skip_frames}th frame")
        
        socketio.emit('video_processing_started', {
            'filepath': filepath,
            'total_frames': total_frames,
            'fps': fps
        })
        
        positions = []
        frame_count = 0
        processed_count = 0
        
        scale_factor = 0.5 
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            
            if frame_count % skip_frames == 0:
                processed_count += 1
                
                h, w = frame.shape[:2]
                resized_frame = cv2.resize(frame, (int(w * scale_factor), int(h * scale_factor)))
                
                tracking_data, display_frame = process_frame(resized_frame, positions)
                
                display_frame = cv2.resize(display_frame, (w, h))
                
                _, buffer = cv2.imencode('.jpg', display_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                frame_base64 = base64.b64encode(buffer).decode('utf-8')
                
                app.logger.debug(f"Emitting frame {frame_count}")
                socketio.emit('video_frame', {
                    'frame': frame_base64,
                    'tracking_data': tracking_data,
                    'progress': {
                        'frame': frame_count,
                        'total': total_frames,
                        'percent': round((frame_count / total_frames) * 100, 1)
                    }
                })
                
                time.sleep(0.05) 
        
        cap.release()
        app.logger.info(f"Video processing complete: {processed_count} frames processed")
        socketio.emit('video_complete', {
            'message': 'Video processing complete',
            'filepath': filepath,
            'frames_processed': processed_count,
            'total_frames': total_frames
        })
    
    except Exception as e:
        app.logger.error(f"Error processing video: {str(e)}")
        socketio.emit('video_error', {'error': f'Error processing video: {str(e)}'})

@socketio.on('start_webcam')
def handle_start_webcam(data=None):
    """Start webcam tracking"""
    global webcam_active, video_cap
    
    webcam_id = 0
    app.logger.info(f"Starting webcam with ID: {webcam_id}")
    
    video_cap = cv2.VideoCapture(webcam_id)
    if not video_cap.isOpened():
        emit('webcam_error', {'error': 'Could not access webcam'})
        return
    
    webcam_active = True
    threading.Thread(target=webcam_loop).start()
    emit('webcam_started', {'message': 'Webcam started successfully'})

def webcam_loop():
    """Main webcam processing loop"""
    global webcam_active, video_cap
    positions = []
    
    while webcam_active and video_cap.isOpened():
        ret, frame = video_cap.read()
        if not ret:
            break
            
        frame = cv2.flip(frame, 1)  
        tracking_data, display_frame = process_frame(frame, positions)
        
        _, buffer = cv2.imencode('.jpg', display_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        socketio.emit('webcam_frame', {
            'frame': frame_base64,
            'tracking_data': tracking_data
        })
        
        time.sleep(0.05) 

@socketio.on('stop_webcam')
def handle_stop_webcam():
    """Stop webcam tracking"""
    global webcam_active, video_cap
    
    webcam_active = False
    if video_cap:
        video_cap.release()
        video_cap = None
    
    emit('webcam_stopped', {'message': 'Webcam stopped'})

@socketio.on('change_unit')
def handle_change_unit(data):
    """Toggle between pixels and mm units"""
    global unit_mode
    
    new_unit = data.get('unit', 'pixels')
    if new_unit in ['pixels', 'mm']:
        unit_mode = new_unit
        emit('unit_changed', {'unit': unit_mode})
    else:
        emit('unit_error', {'error': 'Invalid unit'})

@socketio.on('replay_video')
def handle_replay_video(data):
    """Replay the last uploaded video"""
    filepath = data.get('filepath')
    
    app.logger.info(f"Received replay_video request with filepath: {filepath}")
    
    if not filepath:
        try:
            files = os.listdir(app.config['UPLOAD_FOLDER'])
            if files:
                # Get the most recently modified file
                files.sort(key=lambda x: os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], x)), reverse=True)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], files[0])
                app.logger.info(f"Replaying most recent video: {filepath}")
            else:
                app.logger.error("No videos found in uploads folder")
                emit('video_error', {'error': 'No videos available to replay'})
                return
        except Exception as e:
            app.logger.error(f"Error finding video to replay: {str(e)}")
            emit('video_error', {'error': f'Error finding video to replay: {str(e)}'})
            return
    else:
        if not os.path.isabs(filepath):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filepath)
    
    if not os.path.exists(filepath):
        app.logger.error(f"Video file not found: {filepath}")
        emit('video_error', {'error': f'Video file not found: {filepath}'})
        return
    
    app.logger.info(f"Starting replay of video: {filepath}")
    
    threading.Thread(target=process_uploaded_video, args=(filepath,)).start()
    emit('replay_started', {'message': 'Video replay started', 'filepath': filepath})

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'unit_mode': unit_mode})

if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    import eventlet
    eventlet.monkey_patch()
    
    port = 8080
    print(f"Starting server on port {port}")
    socketio.run(app, debug=True, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)