"""
Goal: Take a `.csv` file stored in Azure Blob Storage as input and convert it to a DataFrame as output.
"""

# Standard library imports
import os
from io import StringIO

# Third-party package imports
import pandas as pd
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient


def parse_torque_events_by_cycle(blob_name: str) -> pd.DataFrame:
    """
    Parse torque events by cycle `.csv` file from Azure Blob Storage and convert it to a DataFrame.

    Azure connection details are read from environment variables:
    - AZURE_STORAGE_CONNECTION_STRING: Azure storage account connection string
    - INPUT_CONTAINER_NAME: Container name in blob storage

    Args:
        blob_name: Name of the blob file in Azure storages (e.g., "torque_events_by_cycle.csv")

    Returns:
        DataFrame with columns: Cycle_ID, Axis, Cycle_Start, Cycle_End, Peak_Torque_pct_of_rated, Related_Error_Code

    Raises:
        EnvironmentError: If required environment variables are not set
        Exception: If Azure blob access fails
    """
    # Load environment variables from `.env` file
    load_dotenv()

    # Get Azure configuration from environment variables
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("INPUT_CONTAINER_NAME")

    # Validate required environment variables
    if not connection_string:
        raise EnvironmentError(
            "AZURE_STORAGE_CONNECTION_STRING environment variable is required"
        )
    if not container_name:
        raise EnvironmentError("INPUT_CONTAINER_NAME environment variable is required")

    try:
        # Connect to Azure Blob Storage
        blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        blob_client = blob_service_client.get_blob_client(
            container=container_name, blob=blob_name
        )

        # Download and decode blob content
        blob_content = blob_client.download_blob().readall().decode("utf-8")

        # Parse CSV content directly into DataFrame
        df = pd.read_csv(StringIO(blob_content))

        # Convert cycle start and cycle end columns to ISO 8601 format
        if "Cycle_Start" in df.columns:
            df["Cycle_Start"] = pd.to_datetime(df["Cycle_Start"]).dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
        if "Cycle_End" in df.columns:
            df["Cycle_End"] = pd.to_datetime(df["Cycle_End"]).dt.strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

        return df

    except Exception as e:
        raise Exception(f"Failed to read from Azure Blob Storage: {e}") from e


# HOW DO WE WIRE THIS COMPONENT INTO THE MAIN METHOD?


class TorqueEventsByCycleCleanup:
    """Class wrapper that provides Azure I/O and processing helpers for torque events by cycle."""

    def __init__(self):
        load_dotenv()

        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        input_container = os.getenv("INPUT_CONTAINER_NAME")
        output_container = os.getenv("OUTPUT_CONTAINER_NAME")

        if not connection_string:
            raise EnvironmentError("AZURE_STORAGE_CONNECTION_STRING environment variable is required")
        if not input_container:
            raise EnvironmentError("INPUT_CONTAINER_NAME environment variable is required")
        if not output_container:
            raise EnvironmentError("OUTPUT_CONTAINER_NAME environment variable is required")

        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        self.input_container_client = self.blob_service_client.get_container_client(input_container)
        self.output_container_client = self.blob_service_client.get_container_client(output_container)

    def process_blob(self, blob_name: str) -> str:
        """Download, parse, normalize, and upload the cleaned CSV. Returns output blob name."""
        # Use the existing parser which reads from the input container
        df = parse_torque_events_by_cycle(blob_name)

        # Ensure columns exist and normalize formatting already done in parser
        # Write DataFrame to CSV bytes
        csv_bytes = df.to_csv(index=False).encode("utf-8")

        base = os.path.splitext(os.path.basename(blob_name))[0]
        output_name = f"{base}.csv"
        out_blob_client = self.output_container_client.get_blob_client(output_name)
        out_blob_client.upload_blob(csv_bytes, overwrite=True)

        return output_name

    def process_all_blobs(self):
        """Process any `torque_events_by_cycle.csv` files found in the input container."""
        found = False
        for blob in self.input_container_client.list_blobs():
            if os.path.basename(blob.name).lower() == "torque_events_by_cycle.csv":
                found = True
                self.process_blob(blob.name)

        if not found:
            raise FileNotFoundError("No torque_events_by_cycle.csv files found in input container")
