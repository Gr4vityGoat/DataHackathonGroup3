/**
 * Torque Time Series Data Cleanup - Frontend JavaScript
 */

// Configuration
const API_BASE = '/api';
const STATUS_CHECK_INTERVAL = 1000; // 1 second
let statusCheckTimer = null;
let filesToUpload = [];

/**
 * Initialize the application
 */
document.addEventListener('DOMContentLoaded', function() {
    checkServiceHealth();
    startStatusPolling();
});

/**
 * Check service health status
 */
function checkServiceHealth() {
    fetch(`${API_BASE}/health`)
        .then(response => response.json())
        .then(data => {
            updateServiceStatus(data.service === 'ready');
        })
        .catch(error => {
            console.error('Health check failed:', error);
            updateServiceStatus(false);
        });
}

/**
 * Update service status display
 */
function updateServiceStatus(isReady) {
    const element = document.getElementById('serviceStatus');
    if (isReady) {
        element.textContent = '🟢 Ready';
        element.className = 'status-value ready';
        document.getElementById('processAllBtn').disabled = false;
        document.getElementById('processSingleBtn').disabled = false;
        // enable specialized buttons when service is available
        const sensorBtn = document.getElementById('processSensorBtn');
        if (sensorBtn) sensorBtn.disabled = false;
        const maintenanceBtn = document.getElementById('processMaintenanceBtn');
        if (maintenanceBtn) maintenanceBtn.disabled = false;
    } else {
        element.textContent = '🔴 Not Available';
        element.className = 'status-value error';
        document.getElementById('processAllBtn').disabled = true;
        document.getElementById('processSingleBtn').disabled = true;
        const sensorBtn = document.getElementById('processSensorBtn');
        if (sensorBtn) sensorBtn.disabled = true;
        const maintenanceBtn = document.getElementById('processMaintenanceBtn');
        if (maintenanceBtn) maintenanceBtn.disabled = true;
    }
}

/**
 * Start polling for status updates
 */
function startStatusPolling() {
    statusCheckTimer = setInterval(updateProcessingStatus, STATUS_CHECK_INTERVAL);
}

/**
 * Stop polling for status updates
 */
function stopStatusPolling() {
    if (statusCheckTimer) {
        clearInterval(statusCheckTimer);
        statusCheckTimer = null;
    }
}

/**
 * Fetch and update processing status
 */
function updateProcessingStatus() {
    fetch(`${API_BASE}/status`)
        .then(response => response.json())
        .then(data => {
            // Update processing status
            const processingElement = document.getElementById('processingStatus');
            if (data.is_processing) {
                processingElement.textContent = '⏳ In Progress';
                processingElement.className = 'status-value processing';
                document.getElementById('processAllBtn').disabled = true;
                document.getElementById('processSingleBtn').disabled = true;
            } else {
                processingElement.textContent = '✓ Not processing';
                processingElement.className = 'status-value ready';
                document.getElementById('processAllBtn').disabled = false;
                document.getElementById('processSingleBtn').disabled = false;
            }

            // Update status message
            const messageElement = document.getElementById('statusMessage');
            if (data.message) {
                messageElement.textContent = data.message;
            }

            // Update progress info
            if (data.current_file) {
                document.getElementById('currentFile').textContent = data.current_file;
            } else {
                document.getElementById('currentFile').textContent = 'None';
            }

            document.getElementById('filesProcessed').textContent = data.files_processed || 0;
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
        })
        .catch(error => {
            console.error('Status update failed:', error);
            document.getElementById('statusMessage').textContent = 'Error fetching status';
        });
}

/**
 * Process all files
 */
function processAllFiles() {
    if (!confirm('Start processing all files in the input container?')) {
        return;
    }

    const button = document.getElementById('processAllBtn');
    button.disabled = true;
    button.textContent = 'Processing...';

    fetch(`${API_BASE}/process`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (response.ok || response.status === 202) {
            showNotification('Processing started. Please monitor the status below.', 'success');
            return response.json();
        } else {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
    })
    .then(data => {
        console.log('Processing response:', data);
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification(`Error starting process: ${error.message}`, 'error');
        button.disabled = false;
        button.textContent = 'Process All Files';
    });
}

/**
 * Toggle single file form visibility
 */
function toggleSingleFileForm() {
    const form = document.getElementById('singleFileForm');
    const isHidden = form.style.display === 'none';
    
    if (isHidden) {
        form.style.display = 'block';
        document.getElementById('filename').focus();
    } else {
        form.style.display = 'none';
        document.getElementById('filename').value = '';
    }
}

/**
 * Process single file
 */
function processSingleFile() {
    const filename = document.getElementById('filename').value.trim();
    
    if (!filename) {
        showNotification('Please enter a filename', 'error');
        return;
    }

    if (!confirm(`Start processing file: ${filename}?`)) {
        return;
    }

    fetch(`${API_BASE}/process-single`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ filename: filename })
    })
    .then(response => {
        if (response.ok || response.status === 202) {
            showNotification(`Processing started for ${filename}`, 'success');
            toggleSingleFileForm();
            return response.json();
        } else {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
    })
    .then(data => {
        console.log('Processing response:', data);
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification(`Error starting process: ${error.message}`, 'error');
    });
}

/**
 * Process sensor readings (specialized handler)
 */
function processSensorReadings() {
    if (!confirm('Start processing sensor_readings.csv?')) {
        return;
    }

    const button = document.getElementById('processSensorBtn');
    button.disabled = true;
    button.textContent = 'Processing...';

    fetch(`${API_BASE}/process-sensor`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (response.ok || response.status === 202) {
            showNotification('Sensor processing started. Monitor status below.', 'success');
            return response.json();
        } else {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
    })
    .then(data => {
        console.log('Sensor processing response:', data);
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification(`Error starting sensor processing: ${error.message}`, 'error');
        button.disabled = false;
        button.textContent = 'Process Sensor Readings';
    });
}


/**
 * Process maintenance notes
 */
function processMaintenanceNotes() {
    if (!confirm('Start processing maintenance_notes.txt?')) {
        return;
    }

    const button = document.getElementById('processMaintenanceBtn');
    if (!button) return;
    button.disabled = true;
    button.textContent = 'Processing...';

    fetch(`${API_BASE}/process-maintenance`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => {
        if (response.ok || response.status === 202) {
            showNotification('Maintenance processing started', 'success');
        } else {
            return response.json().then(data => { throw new Error(data.error || 'Failed to start maintenance processing') });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification(`Error starting maintenance processing: ${error.message}`, 'error');
        button.disabled = false;
        button.textContent = 'Process Maintenance Notes';
    });
}

/**
 * Handle drag over event for file upload
 */
function handleDragOver(event) {
    event.preventDefault();
    const uploadArea = document.getElementById('uploadArea');
    uploadArea.classList.add('dragover');
}

/**
 * Handle drag leave event for file upload
 */
function handleDragLeave(event) {
    event.preventDefault();
    const uploadArea = document.getElementById('uploadArea');
    uploadArea.classList.remove('dragover');
}

/**
 * Handle file drop event
 */
function handleDrop(event) {
    event.preventDefault();
    const uploadArea = document.getElementById('uploadArea');
    uploadArea.classList.remove('dragover');
    
    const files = event.dataTransfer.files;
    handleFiles(files);
}

/**
 * Handle file selection from input
 */
function handleFileSelect(event) {
    const files = event.target.files;
    handleFiles(files);
}

/**
 * Process selected files
 */
function handleFiles(files) {
    filesToUpload = [];

    for (let file of files) {
        // Accept any file type for upload
        filesToUpload.push(file);
    }
    
    if (filesToUpload.length > 0) {
        displayFileList();
    }
}

/**
 * Display the list of files to upload
 */
function displayFileList() {
    const fileList = document.getElementById('fileList');
    const uploadFileList = document.getElementById('uploadFileList');
    
    uploadFileList.innerHTML = '';
    
    filesToUpload.forEach((file, index) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <div>
                <div class="file-name">${file.name}</div>
                <div class="file-size">${formatFileSize(file.size)}</div>
            </div>
            <button class="remove-btn" onclick="removeFile(${index})">Remove</button>
        `;
        uploadFileList.appendChild(li);
    });
    
    fileList.style.display = 'block';
}

/**
 * Remove a file from the upload list
 */
function removeFile(index) {
    filesToUpload.splice(index, 1);
    if (filesToUpload.length === 0) {
        document.getElementById('fileList').style.display = 'none';
        document.getElementById('fileInput').value = '';
    } else {
        displayFileList();
    }
}

/**
 * Clear all files from the upload list
 */
function clearFileList() {
    filesToUpload = [];
    document.getElementById('fileList').style.display = 'none';
    document.getElementById('fileInput').value = '';
}

/**
 * Format file size for display
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * Upload files to Azure Blob Storage
 */
function uploadFiles() {
    if (filesToUpload.length === 0) {
        showNotification('No files to upload', 'error');
        return;
    }
    
    const progressDiv = document.getElementById('uploadProgress');
    const progressFill = document.getElementById('uploadProgressFill');
    const progressText = document.getElementById('uploadProgressText');
    const fileList = document.getElementById('fileList');
    
    progressDiv.style.display = 'block';
    fileList.style.display = 'none';
    
    let uploadedCount = 0;
    const totalFiles = filesToUpload.length;
    
    filesToUpload.forEach((file, index) => {
        const formData = new FormData();
        formData.append('file', file);
        
        fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Failed to upload ${file.name}`);
            }
            return response.json();
        })
        .then(data => {
            uploadedCount++;
            const progress = Math.round((uploadedCount / totalFiles) * 100);
            progressFill.style.width = progress + '%';
            progressText.textContent = `Uploading... ${uploadedCount}/${totalFiles} files`;
            
            if (uploadedCount === totalFiles) {
                progressText.textContent = 'Upload complete!';
                showNotification(`Successfully uploaded ${totalFiles} file(s)`, 'success');
                setTimeout(() => {
                    progressDiv.style.display = 'none';
                    clearFileList();
                }, 2000);
            }
        })
        .catch(error => {
            console.error('Upload error:', error);
            showNotification(`Error uploading ${file.name}: ${error.message}`, 'error');
        });
    });
}

/**
 * Show notification message
 */
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    let bgColor;
    if (type === 'success') {
        bgColor = '#4caf50';
    } else if (type === 'error') {
        bgColor = '#f44336';
    } else if (type === 'warning') {
        bgColor = '#ff9800';
    } else {
        bgColor = '#2196f3';
    }
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        background: ${bgColor};
        color: white;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        z-index: 1000;
        animation: slideIn 0.3s ease-out;
    `;

    document.body.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 5000);
}

/**
 * Add slide-in animation
 */
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
