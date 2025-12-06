"""
Azure Data Cleanup Web Application

Flask-based web interface for the Torque Time Series data cleanup service.
Provides endpoints to trigger cleanup operations and monitor status.
"""

from flask import Flask, render_template, jsonify, request
from src.data_processing.torqueTimeSeries import TorqueTimeSeriesCleanup
import logging
from functools import wraps
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')

# Global service instance
cleanup_service = None
processing_status = {
    'is_processing': False,
    'current_file': None,
    'message': None,
    'files_processed': 0
}


def init_cleanup_service():
    """Initialize the cleanup service."""
    global cleanup_service
    try:
        cleanup_service = TorqueTimeSeriesCleanup()
        logger.info("Cleanup service initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize cleanup service: {e}")
        return False


def require_service(f):
    """Decorator to ensure cleanup service is initialized."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if cleanup_service is None:
            return jsonify({'error': 'Cleanup service not initialized'}), 500
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    """Serve the main web page."""
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def get_status():
    """Get current processing status."""
    return jsonify(processing_status), 200


@app.route('/api/process', methods=['POST'])
@require_service
def process_files():
    """Trigger cleanup processing in background thread."""
    global processing_status
    
    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 400
    
    # Start processing in background thread
    thread = threading.Thread(target=_background_process)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'message': 'Processing started',
        'status': 'processing'
    }), 202


def _background_process():
    """Background task to process files."""
    global processing_status
    
    processing_status['is_processing'] = True
    processing_status['message'] = 'Initializing...'
    processing_status['files_processed'] = 0
    
    try:
        processing_status['message'] = 'Starting batch processing...'
        cleanup_service.process_all_blobs()
        
        processing_status['message'] = 'Processing completed successfully'
        processing_status['files_processed'] = 1
        logger.info("Batch processing completed successfully")
        
    except Exception as e:
        processing_status['message'] = f'Error: {str(e)}'
        logger.error(f"Error during batch processing: {e}")
    
    finally:
        processing_status['is_processing'] = False


@app.route('/api/process-single', methods=['POST'])
@require_service
def process_single_file():
    """Process a specific file by name."""
    data = request.get_json()
    
    if not data or 'filename' not in data:
        return jsonify({'error': 'Filename is required'}), 400
    
    filename = data['filename']
    
    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 400
    
    # Start processing in background thread
    thread = threading.Thread(target=_background_process_single, args=(filename,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'message': f'Processing {filename} started',
        'status': 'processing'
    }), 202


def _background_process_single(filename: str):
    """Background task to process a single file."""
    global processing_status
    
    processing_status['is_processing'] = True
    processing_status['current_file'] = filename
    processing_status['message'] = f'Processing {filename}...'
    
    try:
        cleanup_service.process_blob(filename)
        
        processing_status['message'] = f'{filename} processed successfully'
        processing_status['files_processed'] = 1
        logger.info(f"File {filename} processed successfully")
        
    except Exception as e:
        processing_status['message'] = f'Error processing {filename}: {str(e)}'
        logger.error(f"Error processing {filename}: {e}")
    
    finally:
        processing_status['is_processing'] = False
        processing_status['current_file'] = None


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    service_status = 'ready' if cleanup_service else 'not_initialized'
    return jsonify({
        'status': 'ok',
        'service': service_status
    }), 200


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Initialize the cleanup service
    if not init_cleanup_service():
        logger.warning("Starting app with cleanup service not initialized")
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
