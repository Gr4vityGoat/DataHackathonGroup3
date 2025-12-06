"""
Azure Data Cleanup Web Application

Flask-based web interface for the Torque Time Series data cleanup service.
Provides endpoints to trigger cleanup operations and monitor status.
"""

from flask import Flask, render_template, jsonify, request
from src.data_processing.torqueTimeSeries import TorqueTimeSeriesCleanup
from src.data_processing.sensorReading import SensorReadingsCleanup
from src.data_processing.maintenanceNotes import MaintenanceNotesCleanup
import logging
from functools import wraps
import threading
from werkzeug.utils import secure_filename
import os
from azure.storage.blob import ContentSettings

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


@app.route('/api/process-sensor', methods=['POST'])
def process_sensor_readings():
    """Trigger sensor readings processing in background thread.
    Uses SensorReadingsCleanup which manages its own blob clients.
    """
    global processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 400

    thread = threading.Thread(target=_background_process_sensor)
    thread.daemon = True
    thread.start()

    return jsonify({
        'message': 'Sensor readings processing started',
        'status': 'processing'
    }), 202


@app.route('/api/process-maintenance', methods=['POST'])
def process_maintenance_notes():
    """Trigger maintenance notes processing in background thread.
    Uses MaintenanceNotesCleanup which manages its own blob clients.
    """
    global processing_status

    if processing_status['is_processing']:
        return jsonify({'error': 'Processing already in progress'}), 400

    thread = threading.Thread(target=_background_process_maintenance)
    thread.daemon = True
    thread.start()

    return jsonify({
        'message': 'Maintenance notes processing started',
        'status': 'processing'
    }), 202


def _background_process_sensor():
    """Background task to run SensorReadingsCleanup.process_all_blobs()."""
    global processing_status
    processing_status['is_processing'] = True
    processing_status['message'] = 'Processing sensor readings...'
    processing_status['files_processed'] = 0

    try:
        service = SensorReadingsCleanup()
        service.process_all_blobs()
        processing_status['message'] = 'Sensor processing completed'
        processing_status['files_processed'] = 1
        logger.info('Sensor readings processing completed')
    except Exception as e:
        processing_status['message'] = f'Error: {str(e)}'
        logger.error(f'Error processing sensor readings: {e}')
    finally:
        processing_status['is_processing'] = False


def _background_process_maintenance():
    """Background task to run MaintenanceNotesCleanup.process_all_blobs()."""
    global processing_status
    processing_status['is_processing'] = True
    processing_status['message'] = 'Processing maintenance notes...'
    processing_status['files_processed'] = 0

    try:
        service = MaintenanceNotesCleanup()
        service.process_all_blobs()
        processing_status['message'] = 'Maintenance processing completed'
        processing_status['files_processed'] = 1
        logger.info('Maintenance notes processing completed')
    except Exception as e:
        processing_status['message'] = f'Error: {str(e)}'
        logger.error(f'Error processing maintenance notes: {e}')
    finally:
        processing_status['is_processing'] = False


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


@app.route('/api/upload', methods=['POST'])
@require_service
def upload_file():
    """Upload a file to the input container."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    # Removed CSV-only check to allow any file type

    try:
        filename = secure_filename(file.filename)
        # Read raw bytes so any file type (binary or text) can be uploaded
        file_bytes = file.read()
        
        # Upload to Azure Blob Storage input container preserving content type when possible
        blob_client = cleanup_service.input_container_client.get_blob_client(filename)
        try:
            content_type = file.content_type if hasattr(file, 'content_type') else None
            cs = None
            try:
                if content_type:
                    # attempt to use ContentSettings if available
                    cs = ContentSettings(content_type=content_type)
            except Exception:
                cs = None

            if cs is not None:
                # some SDK versions accept content_settings
                try:
                    blob_client.upload_blob(file_bytes, overwrite=True, content_settings=cs)
                except TypeError:
                    blob_client.upload_blob(file_bytes, overwrite=True)
            else:
                blob_client.upload_blob(file_bytes, overwrite=True)
        except Exception:
            # If anything goes wrong with content settings or upload attempt, try a simple upload
            try:
                blob_client.upload_blob(file_bytes, overwrite=True)
            except Exception:
                raise

        logger.info(f"File uploaded successfully: {filename}")
        return jsonify({
            'message': f'File {filename} uploaded successfully',
            'filename': filename
        }), 200
    except Exception as e:
        logger.exception(f"Error uploading file: {e}")
        return jsonify({'error': f'Error uploading file: {str(e)}'}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    # If the request looks like an API call, return JSON. Otherwise return the SPA index page
    try:
        wants_json = request.path.startswith('/api') or (
            request.accept_mimetypes.best == 'application/json' and
            not request.accept_mimetypes.accept_html
        )
    except Exception:
        wants_json = False

    if wants_json:
        return jsonify({'error': 'Not found'}), 404
    # For browser navigation, return index.html so the frontend can handle routing
    return render_template('index.html'), 200


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
