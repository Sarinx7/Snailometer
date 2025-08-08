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
from flask_cors import CORS
import sys
import io
import eventlet


app = Flask(__name__)
app.config['SECRET_KEY'] = 'snailometer_scret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    async_mode='eventlet',
                    logger=True,
                    engineio_logger=True
                    )


unit_mode = "pixels"
PIXELS_TO_MM = 0.2646
webcam_active = False
video_cap = None 

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def calculate_speed_and_distance(position):

    if len(position) < 2:
        return 0, 0
    
    total_distance = 0
    if len(position) > 1:
        for i in range(1, len(position)):
            x1 , y1 = position[i - 1]
            x2 , y2 = position[i]

            dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            total_distance += dist

    else:
        sample_points = [position[0]]
        for i in range(1, len(sample_points)):
            x1 , y1 = sample_points[i - 1]
            x2 , y2 = sample_points[i]

            dist = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
            total_distance += dist

        total_distance *= 2

    total_distance_mm = total_distance * PIXELS_TO_MM
    total_time = position[-1][2] - position[0][2]
    avg_speed = total_distance / total_time if total_time > 0 else 0

    return total_distance, avg_speed


def convert_units(value):

    if unit_mode == "mm":
        return value * PIXELS_TO_MM
    else: 
        return value

def process_frame(frame, positions):
    #Process a single frame
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
        valid_contours = [c for c in contours if cv2.contourArea(c) > min_area]
        
        if valid_contours:
            largest = max(valid_contours, key=cv2.contourArea)
            area = cv2.contourArea(largest)
            
            if area > min_area and area < (frame.shape[0] * frame.shape[1] * 0.5):  # Not too big
                display_frame = frame.copy()
                
                x, y, w, h = cv2.boundingRect(largest)
                M = cv2.moments(largest)

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
                        dist = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)  # Faster than hypot
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
                    text_color = (0, 255, 255)
                    
                    text_x = x
                    text_y = y - 10 if y > 30 else y + h + 20
                    
                    cv2.rectangle(display_frame, (text_x - 2, text_y - 15), 
                                (text_x + len(speed_text) * 8, text_y + 2), (0, 0, 0), -1)
                    cv2.putText(display_frame, speed_text, (text_x, text_y), font, font_scale, 
                                text_color, text_thickness)

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