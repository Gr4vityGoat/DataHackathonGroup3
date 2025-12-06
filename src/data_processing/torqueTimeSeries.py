"""
Torque Time Series Data Cleanup Service

This service reads torque time series data from Azure Blob Storage,
applies data cleaning rules, and writes cleaned data to output container.

Cleaning rules:
- Timestamp conversion to ISO-8601 format
- Mark records as "missing" if Torque_Nm or Torque_pct_of_rated are empty
"""

import os
import csv
import io
from datetime import datetime, timedelta
from typing import List, Dict
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class TorqueTimeSeriesCleanup:
    """Service to cleanup torque time series data from Azure Blob Storage."""
    
    def __init__(self):
        """Initialize Azure Blob Storage client."""
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not found in environment variables")
        
        self.input_container = os.getenv("INPUT_CONTAINER_NAME", "input")
        self.output_container = os.getenv("OUTPUT_CONTAINER_NAME", "output")
        
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.input_container_client = self.blob_service_client.get_container_client(self.input_container)
        self.output_container_client = self.blob_service_client.get_container_client(self.output_container)
        
        logger.info(f"Connected to Azure Blob Storage")
        logger.info(f"Input container: {self.input_container}, Output container: {self.output_container}")
    
    def convert_timestamp_to_iso8601(self, timestamp_str: str, reference_date: datetime = None) -> str:
        """
        Convert timestamp to ISO-8601 format.
        
        Handles various formats:
        - Full datetime: "11/17/2025 9:00:02 AM"
        - Time only: "00:02.0" (MM:SS.m)
        
        Args:
            timestamp_str: Time string
            reference_date: Optional reference date (defaults to today)
            
        Returns:
            ISO-8601 formatted datetime string
        """
        try:
            if not timestamp_str or not timestamp_str.strip():
                return ''
            
            timestamp_str = timestamp_str.strip()
            
            # Try parsing as full datetime first (MM/DD/YYYY H:MM:SS AM/PM)
            try:
                dt = datetime.strptime(timestamp_str, '%m/%d/%Y %I:%M:%S %p')
                return dt.isoformat()
            except (ValueError, AttributeError):
                pass
            
            # Try parsing as MM:SS.d format
            try:
                if reference_date is None:
                    reference_date = datetime.now().date()
                
                parts = timestamp_str.split(':')
                minutes = int(parts[0])
                seconds_parts = parts[1].split('.')
                seconds = int(seconds_parts[0])
                milliseconds = int(seconds_parts[1]) * 100 if len(seconds_parts) > 1 else 0
                
                dt = datetime.combine(
                    reference_date,
                    datetime.min.time()
                ) + timedelta(minutes=minutes, seconds=seconds, milliseconds=milliseconds)
                
                return dt.isoformat()
            except (ValueError, IndexError):
                pass
            
            # If all parsing fails, return original string
            logger.warning(f"Could not parse timestamp '{timestamp_str}'")
            return timestamp_str
        
        except Exception as e:
            logger.warning(f"Error converting timestamp '{timestamp_str}': {e}")
            return timestamp_str
    
    def clean_row(self, row: Dict[str, str]) -> Dict[str, str]:
        """
        Clean a single row of data.
        
        Args:
            row: Dictionary containing row data with keys: Timestamp, Axis, Torque_Nm, Torque_pct_of_rated
            
        Returns:
            Cleaned row dictionary
        """
        cleaned_row = {}
        
        # Get and convert timestamp
        timestamp = row.get('Timestamp', '').strip()
        cleaned_row['Timestamp'] = self.convert_timestamp_to_iso8601(timestamp) if timestamp else ''
        
        # Get Axis
        axis = row.get('Axis', '').strip()
        cleaned_row['Axis'] = axis
        
        # Get Torque_Nm - mark as missing if empty
        torque_nm = row.get('Torque_Nm', '').strip()
        cleaned_row['Torque_Nm'] = torque_nm if torque_nm else 'missing'
        
        # Get Torque_pct_of_rated - mark as missing if empty
        torque_pct = row.get('Torque_pct_of_rated', '').strip()
        cleaned_row['Torque_pct_of_rated'] = torque_pct if torque_pct else 'missing'
        
        # Determine overall data quality
        if cleaned_row['Torque_Nm'] == 'missing' or cleaned_row['Torque_pct_of_rated'] == 'missing':
            cleaned_row['Data_Quality'] = 'missing'
        else:
            cleaned_row['Data_Quality'] = 'complete'
        
        logger.debug(f"Cleaned row: {cleaned_row}")
        return cleaned_row
    
    def process_csv_file(self, file_content: str) -> List[Dict[str, str]]:
        """
        Process CSV file content and apply cleaning rules.
        
        Args:
            file_content: CSV file content as string
            
        Returns:
            List of cleaned row dictionaries
        """
        cleaned_rows = []
        
        # Parse CSV content
        lines = file_content.strip().split('\n')
        
        if not lines:
            logger.error("CSV file is empty")
            return cleaned_rows
        
        # Detect delimiter (tab or comma)
        header_line = lines[0]
        delimiter = '\t' if '\t' in header_line else ','
        logger.info(f"Detected delimiter: {'tab' if delimiter == '\t' else 'comma'}")
        
        # Parse header
        headers = header_line.split(delimiter)
        headers = [h.strip() for h in headers]
        logger.info(f"CSV headers: {headers}")
        logger.info(f"Total data lines: {len(lines) - 1}")
        
        # Process data rows
        for idx, line in enumerate(lines[1:], start=1):
            if not line.strip():
                logger.warning(f"Skipping empty line {idx}")
                continue
            
            values = line.split(delimiter)
            
            # Log first few rows for debugging
            if idx <= 2:
                logger.info(f"Row {idx} raw values: {values}")
            
            # Create row dictionary
            row = {}
            for i, header in enumerate(headers):
                value = values[i].strip() if i < len(values) else ''
                row[header] = value
            
            if idx <= 2:
                logger.info(f"Row {idx} parsed: {row}")
            
            cleaned_row = self.clean_row(row)
            cleaned_rows.append(cleaned_row)
        
        logger.info(f"Total cleaned rows: {len(cleaned_rows)}")
        return cleaned_rows
    
    def rows_to_csv(self, rows: List[Dict[str, str]], fieldnames: List[str]) -> str:
        """
        Convert list of rows to CSV format with proper tab delimiters.
        
        Args:
            rows: List of row dictionaries
            fieldnames: List of field names in order
            
        Returns:
            CSV formatted string
        """
        output = io.StringIO()
        
        # Ensure correct field order
        fieldnames = ['Timestamp', 'Axis', 'Torque_Nm', 'Torque_pct_of_rated', 'Data_Quality']
        
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter='\t', lineterminator='\n')
        writer.writeheader()
        
        for row in rows:
            # Ensure all fields exist in row
            for field in fieldnames:
                if field not in row:
                    row[field] = ''
            writer.writerow(row)
        
        return output.getvalue()
    
    def process_blob(self, blob_name: str) -> None:
        """
        Download blob from input container, clean it, and upload to output container.
        
        Args:
            blob_name: Name of the blob to process
        """
        try:
            logger.info(f"Processing blob: {blob_name}")
            
            # Download blob from input container
            blob_client = self.input_container_client.get_blob_client(blob_name)
            blob_data = blob_client.download_blob()
            file_content = blob_data.readall().decode('utf-8')
            
            # Clean the data
            cleaned_rows = self.process_csv_file(file_content)
            
            if not cleaned_rows:
                logger.warning(f"No data to write for {blob_name}")
                return
            
            # Define fieldnames in correct order
            fieldnames = ['Timestamp', 'Axis', 'Torque_Nm', 'Torque_pct_of_rated', 'Data_Quality']
            
            # Convert to CSV format
            output_csv = self.rows_to_csv(cleaned_rows, fieldnames)
            
            # Upload to output container
            output_blob_client = self.output_container_client.get_blob_client(blob_name)
            output_blob_client.upload_blob(output_csv, overwrite=True)
            
            logger.info(f"Successfully processed and uploaded: {blob_name}")
            logger.info(f"Cleaned {len(cleaned_rows)} rows")
            
        except Exception as e:
            logger.error(f"Error processing blob {blob_name}: {e}")
            raise
    
    def process_all_blobs(self) -> None:
        """Process all blobs in the input container."""
        try:
            logger.info("Starting batch processing of all blobs in input container")
            
            blobs = self.input_container_client.list_blobs()
            blob_count = 0
            
            for blob in blobs:
                if blob.name == 'torque_timeseries.csv':
                    self.process_blob(blob.name)
                    blob_count += 1
            
            logger.info(f"Batch processing completed. Processed {blob_count} CSV files")
            
        except Exception as e:
            logger.error(f"Error during batch processing: {e}")
            raise


if __name__ == "__main__":
    try:
        cleanup_service = TorqueTimeSeriesCleanup()
        cleanup_service.process_all_blobs()
    except Exception as e:
        logger.error(f"Service failed: {e}")
        raise
