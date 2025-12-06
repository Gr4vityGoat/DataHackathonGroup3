"""
Maintenance Notes Cleanup Service

Reads `maintenance_notes.txt` from the input container, parses each line into
three columns and writes a cleaned tab-delimited CSV to the output container.

Output columns:
- Timestamp: ISO-8601 (UTC) datetime string (date at midnight, Z suffix)
- action_taken: short description of the action
- axis: axis number (integer) or empty string if not found

Expected input line example:
  2025-11-17 - Checked belts on axis 6.

"""

import os
import io
import re
import logging
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class MaintenanceNotesCleanup:
    """Process maintenance notes stored as plain text in blob storage."""

    LINE_RE = re.compile(r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s*-\s*(?P<action>.*?)(?:\s+on\s+axis\s+(?P<axis>\d+))?\.?\s*$", re.IGNORECASE)

    def __init__(self):
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

    def parse_line(self, line: str) -> Dict[str, str]:
        """Parse a single maintenance line into fields.

        Returns a dict with keys: Timestamp, action_taken, axis
        """
        line = line.strip()
        if not line:
            return None

        m = self.LINE_RE.match(line)
        if not m:
            # Fallback: try to extract date then everything else as action
            parts = line.split('-', 1)
            if len(parts) == 2:
                date_part = parts[0].strip()
                action_part = parts[1].strip()
                axis = ''
                axis_search = re.search(r"axis\s*(\d+)", action_part, re.IGNORECASE)
                if axis_search:
                    axis = axis_search.group(1)
                    # remove 'on axis X' from action
                    action_part = re.sub(r"on\s+axis\s*\d+", "", action_part, flags=re.IGNORECASE).strip()
                try:
                    dt = datetime.strptime(date_part, "%Y-%m-%d")
                    ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    ts = date_part
                return {"Timestamp": ts, "action_taken": action_part, "axis": axis}

            # Cannot parse
            return {"Timestamp": "", "action_taken": line, "axis": ""}

        date_str = m.group('date')
        action = m.group('action').strip()
        axis = m.group('axis') or ''

        # normalize axis
        axis = axis.strip()

        # convert date to ISO-8601 (midnight UTC)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            ts = date_str

        return {"Timestamp": ts, "action_taken": action, "axis": axis}

    def lines_to_tsv(self, rows: List[Dict[str, str]]) -> str:
        output = io.StringIO()
        header = ['Timestamp', 'action_taken', 'axis']
        output.write('\t'.join(header) + '\n')
        for r in rows:
            # ensure values don't contain tabs or newlines
            vals = [ (r.get(c,'') or '').replace('\t',' ').replace('\n',' ').strip() for c in header ]
            output.write('\t'.join(vals) + '\n')
        return output.getvalue()

    def process_blob(self, blob_name: str) -> None:
        """Download blob, parse maintenance lines, and upload CSV."""
        try:
            logger.info(f"Processing blob: {blob_name}")
            blob_client = self.input_container_client.get_blob_client(blob_name)
            content = blob_client.download_blob().readall().decode('utf-8')

            lines = content.splitlines()
            parsed = []
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                p = self.parse_line(line)
                if p:
                    parsed.append(p)

            if not parsed:
                logger.warning(f"No parsed rows for {blob_name}")
                return

            tsv = self.lines_to_tsv(parsed)

            # Upload to output container with .csv extension
            out_name = os.path.splitext(blob_name)[0] + '.csv'
            out_client = self.output_container_client.get_blob_client(out_name)
            out_client.upload_blob(tsv.encode('utf-8'), overwrite=True)

            logger.info(f"Uploaded cleaned maintenance notes to {out_name} ({len(parsed)} rows)")

        except Exception as e:
            logger.error(f"Error processing blob {blob_name}: {e}")
            raise

    def process_all_blobs(self) -> None:
        """Process exactly the `maintenance_notes.txt` file in the input container."""
        try:
            logger.info("Starting maintenance notes processing")
            blobs = self.input_container_client.list_blobs()
            count = 0
            for blob in blobs:
                if blob.name == 'maintenance_notes.txt' or blob.name.endswith('maintenance_notes.txt'):
                    self.process_blob(blob.name)
                    count += 1
            logger.info(f"Completed maintenance processing. Processed {count} file(s)")
        except Exception as e:
            logger.error(f"Error during batch processing: {e}")
            raise


if __name__ == '__main__':
    svc = MaintenanceNotesCleanup()
    svc.process_all_blobs()
