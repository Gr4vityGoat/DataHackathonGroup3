import os
import re
import io
import csv
import logging
import datetime

from azure.storage.blob import BlobServiceClient, ContentSettings

logger = logging.getLogger(__name__)


class SystemAlertsCleanup:
    """Parses `system_alerts.txt` files where each line is of the form:
    "HH:MM:SS LEVEL: Message text"

    Output: CSV with columns `timestamp,level,message` where `timestamp` is
    normalized to ISO-8601 (YYYY-MM-DDTHH:MM:SSZ). If a line cannot be
    parsed, its fields are replaced with 'missing' and the original text is
    stored in `message`.
    """

    LINE_RE = re.compile(r"^\s*(\d{1,2}:\d{2}:\d{2})\s+([A-Z]+):\s*(.+)$")

    def __init__(self):
        conn_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        input_container = os.environ.get('INPUT_CONTAINER_NAME', 'input')
        output_container = os.environ.get('OUTPUT_CONTAINER_NAME', 'output')

        if not conn_str:
            raise RuntimeError('AZURE_STORAGE_CONNECTION_STRING is not set')

        self.blob_service = BlobServiceClient.from_connection_string(conn_str)
        self.input_container_client = self.blob_service.get_container_client(input_container)
        self.output_container_client = self.blob_service.get_container_client(output_container)
        logger.info("Connected to Azure Blob Storage")
        logger.info(f"Input container: {input_container}, Output container: {output_container}")

    def _line_to_row(self, line, reference_date=None):
        """Parse a single alert line into (timestamp, level, message) tuple."""
        m = self.LINE_RE.match(line)
        if not m:
            return ('missing', 'missing', line.strip())

        time_str, level, message = m.groups()

        # Use provided reference_date or today's date
        if reference_date is None:
            reference_date = datetime.date.today()

        try:
            t = datetime.datetime.strptime(time_str, '%H:%M:%S').time()
            dt = datetime.datetime.combine(reference_date, t)
            # Emit UTC-like ISO with Z (naive -> assume local day/time)
            iso = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        except Exception:
            iso = 'missing'

        return (iso, level, message.strip())

    def process_blob(self, blob_name: str):
        """Download blob, parse alerts, and upload CSV to output container."""
        blob_client = self.input_container_client.get_blob_client(blob_name)
        downloader = blob_client.download_blob()
        raw = downloader.readall()

        try:
            text = raw.decode('utf-8')
        except Exception:
            text = raw.decode('utf-8', errors='replace')

        lines = text.splitlines()
        rows = []
        ref_date = datetime.date.today()

        for ln in lines:
            if not ln.strip():
                continue
            row = self._line_to_row(ln, reference_date=ref_date)
            rows.append(row)

        # Write CSV to memory
        out_buf = io.StringIO()
        writer = csv.writer(out_buf)
        writer.writerow(['timestamp', 'level', 'message'])
        for r in rows:
            writer.writerow(r)

        data = out_buf.getvalue().encode('utf-8')

        # Output filename: replace .txt with .csv
        out_name = os.path.splitext(os.path.basename(blob_name))[0] + '.csv'
        out_blob_client = self.output_container_client.get_blob_client(out_name)
        out_blob_client.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type='text/csv'))

        logger.info(f"Successfully processed and uploaded: {out_name}")
        logger.info(f"Parsed {len(rows)} alert rows")
        return out_name, len(rows)

    def process_all_blobs(self):
        """Find files named `system_alerts.txt` (case-insensitive) and process them."""
        processed = 0
        try:
            for b in self.input_container_client.list_blobs():
                if os.path.basename(b.name).lower() == 'system_alerts.txt':
                    try:
                        self.process_blob(b.name)
                        processed += 1
                    except Exception as e:
                        logger.error(f"Failed to process blob {b.name}: {e}")
        except Exception as e:
            logger.error(f"Error listing blobs: {e}")
            raise
        
        logger.info(f"System alerts: processed {processed} blobs")
        return processed


if __name__ == "__main__":
    try:
        service = SystemAlertsCleanup()
        service.process_all_blobs()
    except Exception as e:
        logger.error(f"Service failed: {e}")
        raise
 