
const socketUrl = window.SERVER_URL || (window.location.protocol + '//' + window.location.hostname + ':8080');

console.log('Connecting Socket.IO to:', socketUrl);


const socket = io(socketUrl, {
    transports: ['websocket', 'polling'],
    reconnectionAttempts: 5,
    reconnectionDelay: 1000,
    forceNew: true,
    autoConnect: true
});


// DEBUGGGING SOCKET (ERROR CHECKING)

socket.on('connect_error', (error) => {
    console.error('Socket.IO connection error:', error);
    showStatusMessage('Connection error. Please refresh the page.', 'error');
});

socket.on('reconnect', (attemptNumber) => {
    showStatusMessage('Reconnected to server!', 'success');
});

socket.on('reconnect_error', (error) => {
    console.error('Socket.IO reconnection error:', error);
    showStatusMessage('Failed to reconnect. Try refreshing the page.', 'error');
});

socket.on('disconnect', (reason) => {
    if (reason === 'io server disconnect') {
        socket.connect();
    }
});

let currentUnit = 'pixels';
let isTracking = false;
let trackingMode = null; 
let lastUploadedVideoPath = null; 
const introLogo = document.getElementById('intro-logo');
const landingContent = document.getElementById('landing-content');
const mainContent = document.getElementById('main-content');
const trackingContent = document.getElementById('tracking-content');
const startButton = document.getElementById('start-button');
const uploadVideoBtn = document.getElementById('upload-video');
const useWebcamBtn = document.getElementById('use-webcam');
const changeUnitBtn = document.getElementById('change-unit');
const videoFileInput = document.getElementById('video-file-input');
const backButton = document.getElementById('back-button');
const stopTrackingBtn = document.getElementById('stop-tracking');
const toggleUnitBtn = document.getElementById('toggle-unit');
const replayVideoBtn = document.getElementById('replay-video');
const videoFeed = document.getElementById('video-feed');
const currentSpeedEl = document.getElementById('current-speed');
const totalDistanceEl = document.getElementById('total-distance');
const avgSpeedEl = document.getElementById('avg-speed');

window.onload = function() {
    setTimeout(function() {
        introLogo.style.display = 'none';
        landingContent.style.display = 'block';
    }, 4000);
};

startButton.onclick = function() {
    landingContent.style.display = 'none';
    mainContent.style.display = 'block';
};

backButton.onclick = function() {
    stopCurrentTracking();
    trackingContent.style.display = 'none';
    mainContent.style.display = 'block';
};

uploadVideoBtn.onclick = function() {
    videoFileInput.click();
};

videoFileInput.onchange = function(event) {
    const file = event.target.files[0];
    if (file) {
        uploadVideo(file);
    }
};

function uploadVideo(file) {
    const formData = new FormData();
    formData.append('video', file);
    
    showStatusMessage('Uploading video...', 'status');
    
    const uploadUrl = (window.SERVER_URL || (window.location.protocol + '//' + window.location.hostname + ':8080')) + '/upload_video';
    
    fetch(uploadUrl, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            showStatusMessage(data.error, 'error');
        } else {
            showStatusMessage('Video uploaded! Starting analysis...', 'success');
            lastUploadedVideoPath = data.filename;
            startVideoTracking();
        }
    })
    .catch(error => {
        console.error('Upload error:', error);
        showStatusMessage('Upload failed: ' + error.message, 'error');
    });
}

useWebcamBtn.onclick = function() {
    startWebcamTracking();
};

function startWebcamTracking() {
    trackingMode = 'webcam';
    showTrackingInterface();
    showStatusMessage('Starting webcam...', 'status');
    socket.emit('start_webcam');
}

function startVideoTracking() {
    trackingMode = 'video';
    showTrackingInterface();
    
    if (replayVideoBtn) {
        replayVideoBtn.style.display = 'block';
    }
}

function showTrackingInterface() {
    mainContent.style.display = 'none';
    trackingContent.style.display = 'block';
    isTracking = true;
    updateControlButtons();
}

function stopCurrentTracking() {
    if (trackingMode === 'webcam') {
        socket.emit('stop_webcam');
    }
    isTracking = false;
    trackingMode = null;
    updateControlButtons();
}

stopTrackingBtn.onclick = function() {
    stopCurrentTracking();
    trackingContent.style.display = 'none';
    mainContent.style.display = 'block';
};

changeUnitBtn.onclick = toggleUnit;
toggleUnitBtn.onclick = toggleUnit;

function toggleUnit() {
    const newUnit = currentUnit === 'pixels' ? 'mm' : 'pixels';
    socket.emit('change_unit', { unit: newUnit });
}

function updateControlButtons() {
    const unitText = currentUnit === 'pixels' ? 'pixel per second' : 'mm per second';
    changeUnitBtn.textContent = unitText;
    
    const toggleText = currentUnit === 'pixels' ? 'switch to mm' : 'switch to pixels';
    toggleUnitBtn.textContent = toggleText;
    
    if (trackingMode === 'video') {
        replayVideoBtn.style.display = 'block';
    } else {
        replayVideoBtn.style.display = 'none';
    }
}

replayVideoBtn.onclick = function() {
    replayVideo();

    resetTrackingState();
};

function replayVideo() {
    showStatusMessage('Replaying video...', 'status');
    socket.emit('replay_video', {});
}

function resetTrackingState() {
    currentSpeedEl.textContent = '0 ' + (currentUnit === 'pixels' ? 'px/s' : 'mm/s');
    totalDistanceEl.textContent = '0 ' + (currentUnit === 'pixels' ? 'px' : 'mm');
    avgSpeedEl.textContent = '0 ' + (currentUnit === 'pixels' ? 'px/s' : 'mm/s');
    
    updateVideoFeed.hasReceivedFrame = false;
}

socket.on('replay_started', function(data) {
    showStatusMessage('Video replay started!', 'success');
    
    trackingMode = 'video';
    showTrackingInterface();
    updateControlButtons();
});
socket.on('webcam_started', function(data) {
    showStatusMessage('Webcam started successfully!', 'success');
});

socket.on('webcam_error', function(data) {
    showStatusMessage(data.error, 'error');
});

socket.on('webcam_stopped', function(data) {
    showStatusMessage('Webcam stopped', 'status');
});

socket.on('webcam_frame', function(data) {
    updateVideoFeed(data.frame);
    updateTrackingStats(data.tracking_data);
});

socket.on('video_frame', function(data) {
    videoFeed.classList.remove('loading');
    
    updateVideoFeed(data.frame);
    updateTrackingStats(data.tracking_data);
    
    if (data.progress) {
        const percent = data.progress.percent;
    }
});

socket.on('video_complete', function(data) {
    showStatusMessage(`Video analysis complete! Processed ${data.frames_processed} frames.`, 'success');
    
    if (replayVideoBtn) {
        replayVideoBtn.classList.add('highlight-button');
        setTimeout(() => {
            replayVideoBtn.classList.remove('highlight-button');
        }, 2000);
    }
});

socket.on('video_processing_started', function(data) {
    showStatusMessage(`Processing video with ${data.total_frames} frames...`, 'status');
    
    videoFeed.classList.add('loading');
});

socket.on('video_error', function(data) {
    showStatusMessage('Video error: ' + data.error, 'error');
});

socket.on('unit_changed', function(data) {
    currentUnit = data.unit;
    updateControlButtons();
    showStatusMessage(`Unit changed to: ${currentUnit}`, 'success');
});

socket.on('unit_error', function(data) {
    showStatusMessage(data.error, 'error');
});

function updateVideoFeed(frameData) {
    videoFeed.src = 'data:image/jpeg;base64,' + frameData;
    
    if (!updateVideoFeed.hasReceivedFrame) {
        updateVideoFeed.hasReceivedFrame = true;
        console.log('First video frame received and displayed');
        showStatusMessage('Video feed connected!', 'success');
    }
}

function updateTrackingStats(data) {
    const unit = data.unit === 'pixels' ? 'px' : 'mm';
    
    currentSpeedEl.textContent = `${data.speed} ${unit}/s`;
    totalDistanceEl.textContent = `${data.total_distance} ${unit}`;
    avgSpeedEl.textContent = `${data.avg_speed} ${unit}/s`;
    
    if (data.detected) {
        currentSpeedEl.style.color = '#BEA1CC';
    } else {
        currentSpeedEl.style.color = '#999';
    }
}

function showStatusMessage(message, type) {
    if (type === 'error') {
        console.error('Status:', message);
    }
    
    const existingMessages = document.querySelectorAll('.status-message');
    existingMessages.forEach(msg => msg.remove());
    
    const statusDiv = document.createElement('div');
    statusDiv.className = `status-message ${type}-message`;
    statusDiv.textContent = message;
    
    const container = isTracking ? 
        document.getElementById('tracking-container') : 
        document.getElementById('main-container');
    
    container.appendChild(statusDiv);
    
    setTimeout(() => {
        if (statusDiv.parentNode) {
            statusDiv.remove();
        }
    }, 5000);
}

document.body.style.overflow = 'hidden';

updateControlButtons();
