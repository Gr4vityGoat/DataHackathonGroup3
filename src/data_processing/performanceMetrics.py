"""
Performance Metrics Data Cleanup Service (Pandas)
 
This service reads performance metrics time series data from Azure Blob Storage,
applies data cleaning rules, and writes cleaned data to the output container.
 
Cleaning rules:
- Timestamp conversion to ISO-8601 UTC (Zulu) as 'timestamp_utc'
- If Metric2, Metric3, Metric4 are missing -> label as "missing"
- Prefer spaces as delimiters; gracefully fallback to comma-delimited
"""
 
import os
import io
import logging
from datetime import timezone, timedelta
 
import pandas as pd
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, BlobClient
 
# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PerformanceMetricsCleanup")
 
# ---------- Environment ----------
load_dotenv()
 
class PerformanceMetricsCleanup:
    """Service to cleanup performance metrics data from Azure Blob Storage."""
 
    def __init__(self):
        # ---- Azure Blob Storage connection ----
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not found in environment variables")
 
        self.input_container = os.getenv("INPUT_CONTAINER_NAME", "input")
        self.output_container = os.getenv("OUTPUT_CONTAINER_NAME", "output")
 
        # Timestamp source timezone: fixed offset in hours (e.g., -6)
        self.source_tz_offset_hours = int(os.getenv("SOURCE_TIMEZONE_OFFSET_HOURS", "-6"))
 
        # Filter: exact blob name or prefix (default: performance_metrics.csv)
        self.input_blob_filter = os.getenv("INPUT_BLOB_FILTER", "performance_metrics.csv")
 
        # Clients
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.input_container_client = self.blob_service_client.get_container_client(self.input_container)
        self.output_container_client = self.blob_service_client.get_container_client(self.output_container)
 
        logger.info("Connected to Azure Blob Storage")
        logger.info(f"Input container: {self.input_container} | Output container: {self.output_container}")
        logger.info(f"Source timezone offset (hours): {self.source_tz_offset_hours}")
        logger.info(f"Blob filter: {self.input_blob_filter}")
 
    # ---------- CSV reader that prefers spaces, falls back to comma ----------
    def _read_csv_space_first(self, in_stream: io.BytesIO) -> pd.DataFrame:
        in_stream.seek(0)
        try:
            df = pd.read_csv(in_stream, sep=r"\s+", engine="python")
            df.columns = [c.strip() for c in df.columns]
            if "Timestamp" not in df.columns:
                raise ValueError("Space parse did not yield 'Timestamp' column; falling back to comma.")
            logger.info("Parsed as space-delimited")
            return df
        except Exception as e:
            logger.info(f"Space parse failed ({e}); falling back to comma-delimited")
            in_stream.seek(0)
            df = pd.read_csv(in_stream)
            df.columns = [c.strip() for c in df.columns]
            return df
 
    # ---------- Core normalization (pandas) ----------
    def normalize_df(self, df: pd.DataFrame) -> pd.DataFrame:
        # Ensure required column exists
        if "Timestamp" not in df.columns:
            raise ValueError("Missing 'Timestamp' column in input CSV")
 
        # Timestamp → ISO-8601 UTC
        s = pd.to_datetime(df["Timestamp"], errors="coerce")
        fixed_tz = timezone(timedelta(hours=self.source_tz_offset_hours))
        s_localized = s.dt.tz_localize(fixed_tz)
        s_utc = s_localized.dt.tz_convert(timezone.utc)
        df["timestamp_utc"] = s_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
 
        # Metrics: missing → "missing"
        for col in ["Metric2", "Metric3", "Metric4"]:
            if col in df.columns:
                df[col] = df[col].where(~df[col].isna(), other="missing")
 
        # Put timestamp first for convenience
        df = df[["timestamp_utc"] + [c for c in df.columns if c != "timestamp_utc"]]
        return df
 
    def process_blob(self, blob_name: str) -> None:
        """Download blob, normalize, and upload to output container."""
        try:
            logger.info(f"Processing blob: {blob_name}")
 
            # ---- Download source CSV ----
            in_client: BlobClient = self.input_container_client.get_blob_client(blob_name)
            in_stream = io.BytesIO()
            in_client.download_blob().readinto(in_stream)
            in_stream.seek(0)
 
            # Load with preferred space-delimited reader (fallback to comma)
            df = self._read_csv_space_first(in_stream)
 
            # ---- Normalize ----
            df_norm = self.normalize_df(df)
 
            # ---- Write to CSV (memory) ----
            out_stream = io.BytesIO()
            df_norm.to_csv(out_stream, index=False)
            out_stream.seek(0)
 
            # ---- Upload normalized ----
            out_blob_name = blob_name.replace(".csv", "_normalized.csv")
            out_client = self.output_container_client.get_blob_client(out_blob_name)
            out_client.upload_blob(out_stream.getvalue(), overwrite=True)
 
            # ---- Stats ----
            logger.info(f"Uploaded cleaned blob: {self.output_container}/{out_blob_name}")
            logger.info(f"Rows cleaned: {len(df_norm)}")
            for col in ["Metric2", "Metric3", "Metric4"]:
                if col in df_norm.columns:
                    logger.info(f"{col} 'missing': {(df_norm[col] == 'missing').sum()}")
 
        except Exception as e:
            logger.error(f"Error processing blob {blob_name}: {e}")
            raise
 
    def process_all_blobs(self) -> None:
        """Process all blobs that match the filter in the input container."""
        try:
            logger.info("Starting batch processing of input container")
            count = 0
            for blob in self.input_container_client.list_blobs():
                if blob.name == self.input_blob_filter or blob.name.startswith(self.input_blob_filter):
                    self.process_blob(blob.name)
                    count += 1
            logger.info(f"Batch completed. Processed {count} CSV file(s)")
        except Exception as e:
            logger.error(f"Batch processing error: {e}")
            raise
 
 
if __name__ == "__main__":
    try:
        service = PerformanceMetricsCleanup()
        service.process_all_blobs()
    except Exception as e:
        logger.error(f"Service failed: {e}")
        raise
 