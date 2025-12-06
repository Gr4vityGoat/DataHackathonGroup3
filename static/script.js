/**
 * Torque Time Series Data Cleanup - Frontend JavaScript
 */

// Configuration
const API_BASE = '/api';
const STATUS_CHECK_INTERVAL = 1000; // 1 second
let statusCheckTimer = null;

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
    } else {
        element.textContent = '🔴 Not Available';
        element.className = 'status-value error';
        document.getElementById('processAllBtn').disabled = true;
        document.getElementById('processSingleBtn').disabled = true;
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
 * Show notification message
 */
function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        background: ${type === 'success' ? '#4caf50' : type === 'error' ? '#f44336' : '#2196f3'};
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
