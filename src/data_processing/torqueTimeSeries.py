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
        
        Handles formats like "00:02.0" (MM:SS.m) and converts to ISO-8601.
        If reference_date is provided, uses that date. Otherwise uses today's date.
        
        Args:
            timestamp_str: Time string in format MM:SS.d
            reference_date: Optional reference date (defaults to today)
            
        Returns:
            ISO-8601 formatted datetime string
        """
        try:
            if reference_date is None:
                reference_date = datetime.now().date()
            
            # Parse the timestamp format MM:SS.d
            parts = timestamp_str.strip().split(':')
            minutes = int(parts[0])
            seconds_parts = parts[1].split('.')
            seconds = int(seconds_parts[0])
            milliseconds = int(seconds_parts[1]) * 100 if len(seconds_parts) > 1 else 0
            
            # Create datetime object
            dt = datetime.combine(
                reference_date,
                datetime.min.time()
            ) + timedelta(minutes=minutes, seconds=seconds, milliseconds=milliseconds)
            
            # Return ISO-8601 format
            return dt.isoformat()
        
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return timestamp_str
    
    def clean_row(self, row: Dict[str, str]) -> Dict[str, str]:
        """
        Clean a single row of data.
        
        Args:
            row: Dictionary containing row data
            
        Returns:
            Cleaned row dictionary
        """
        cleaned_row = row.copy()
        
        # Convert timestamp to ISO-8601
        if 'Timestamp' in cleaned_row:
            cleaned_row['Timestamp'] = self.convert_timestamp_to_iso8601(cleaned_row['Timestamp'])
        
        # Check if either Torque_Nm or Torque_pct_of_rated are missing
        torque_nm = cleaned_row.get('Torque_Nm', '').strip()
        torque_pct = cleaned_row.get('Torque_pct_of_rated', '').strip()
        
        if not torque_nm or not torque_pct:
            cleaned_row['Data_Quality'] = 'missing'
        else:
            cleaned_row['Data_Quality'] = 'complete'
        
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
        
        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(file_content), delimiter='\t')
        
        if csv_reader.fieldnames is None:
            logger.error("CSV file has no headers")
            return cleaned_rows
        
        for row in csv_reader:
            cleaned_row = self.clean_row(row)
            cleaned_rows.append(cleaned_row)
        
        return cleaned_rows
    
    def rows_to_csv(self, rows: List[Dict[str, str]], fieldnames: List[str]) -> str:
        """
        Convert list of rows to CSV format.
        
        Args:
            rows: List of row dictionaries
            fieldnames: List of field names in order
            
        Returns:
            CSV formatted string
        """
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
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
            
            # Get fieldnames for CSV output
            fieldnames = list(cleaned_rows[0].keys())
            
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


def main():
    """Main entry point for the cleanup service."""
    try:
        cleanup_service = TorqueTimeSeriesCleanup()
        cleanup_service.process_all_blobs()
    except Exception as e:
        logger.error(f"Service failed: {e}")
        raise


if __name__ == "__main__":
    main()
