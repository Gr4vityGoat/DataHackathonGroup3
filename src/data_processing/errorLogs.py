"""
# Goal: Take a `.txt` file stored in Azure Blob Storage as input and converts it to a DataFrame as output.

# Process:
# 1. Write each line from the `.txt` file to `df["raw_text"]`.
# 2. Identify dates in `df["raw_text"]`. These dates could be in one of three formats: YYYY-MM-DD, YYYY/MM/DD, or NULL. Write date to `df["date"]`.
# 3. Identify times in `df["raw_text"]`. These times could be in one of three formats: HH:MM:SS, HH:MM, or NULL. Write time to `df["time"]`.
# 4. Identify error codes in `df["raw_text"]`. These codes are in the following format: 8-character string, 1st 4 characters are uppercase letters, 5th character is a hyphen, last 3 characters are digits. Write error code to `df["error_code"]`.
# 5. Identify error messages in `df["raw_text"]`. Remove dates, times, and error codes from raw text. Trim trailing and leading whitespace from what is left. Write what is left to `df["error_msg"].`
# 6. Combine `df["date"]` and `df["time"]` into `df["timestamp"]`. `df["timestamp"]` must be ISO 8601-compliant.
"""

# Standard library imports
import re
from typing import Optional
import os

# Third-party package imports
import pandas as pd
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Configuration
DATE_PATTERN = r"\d{4}[-/]\d{2}[-/]\d{2}"  # Pattern for YYYY-MM-DD or YYYY/MM/DD
TIME_PATTERN = r"\[?(\d{2}:\d{2}(?::\d{2})?)\]?"  # Pattern for HH:MM:SS or HH:MM
ERROR_CODE_PATTERN = (
    r"[A-Z]{4}-\d{3}"  # Pattern for 4 uppercase letters, hyphen, 3 digits
)


def extract_date(text: str) -> Optional[str]:
    """
    Extract date from text in format YYYY-MM-DD or YYYY/MM/DD.
    Returns None if no date found.
    """

    match = re.search(DATE_PATTERN, text)
    if not match:
        return None
    # Normalize separator to hyphen
    return match.group(0).replace('/', '-')


def extract_time(text: str) -> Optional[str]:
    """
    Extract time from text in format HH:MM:SS or HH:MM.
    Can be in brackets [HH:MM:SS] or standalone.
    Returns None if no time found.
    """

    match = re.search(TIME_PATTERN, text)
    return match.group(1) if match else None


def extract_error_code(text: str) -> Optional[str]:
    """
    Extract error code in format XXXX-### where:
    - First 4 characters are uppercase letters
    - 5th character is a hyphen
    - Last 3 characters are digits
    Returns None if no error code found.
    """

    match = re.search(ERROR_CODE_PATTERN, text)
    return match.group(0) if match else None


def extract_error_message(
    text: str, date: Optional[str], time: Optional[str], error_code: Optional[str]
) -> str:
    """
    Extract error message by removing date, time, and error code from text.
    Removes common separators (-, :, ,) and trims whitespace.
    """
    message = text

    # Remove the exact date substring if present (normalized date may differ in separators)
    if date:
        message = re.sub(re.escape(date), "", message)

    # Remove any bracketed or standalone time patterns (handles [HH:MM[:SS]] and HH:MM[:SS])
    message = re.sub(r"\[?\d{2}:\d{2}(?::\d{2})?\]?", "", message)

    # Remove error code token if present
    if error_code:
        message = re.sub(re.escape(error_code), "", message)

    # Remove quotes, stray commas, brackets, colons, dashes at edges and extra whitespace
    message = message.replace('"', '')
    message = message.replace("[", "")
    message = message.replace("]", "")
    message = re.sub(r"^[\s\-:,]+", "", message)
    message = re.sub(r"[\s\-:,]+$", "", message)
    message = re.sub(r",+", ",", message)
    message = re.sub(r"\s+", " ", message)

    return message.strip()


def extract_timestamp(date: Optional[str], time: Optional[str]) -> Optional[str]:
    """
    Combine date and time into an ISO 8601-compliant timestamp.

    Args:
        date: Date string in format YYYY-MM-DD or YYYY/MM/DD, or None
        time: Time string in format HH:MM:SS or HH:MM, or None

    Returns:
        ISO 8601 timestamp string (YYYY-MM-DDTHH:MM:SS) or None if no date
    """
    if not date:
        return None

    # Normalize date format to YYYY-MM-DD
    normalized_date = date.replace("/", "-")

    if time:
        # Ensure time has seconds (add :00 if only HH:MM)
        if len(time.split(":")) == 2:
            normalized_time = time + ":00"
        else:
            normalized_time = time

        # Combine date and time in ISO 8601 format
        return f"{normalized_date}T{normalized_time}"
    else:
        # If no time, use midnight
        return f"{normalized_date}T00:00:00"


def parse_error_log(blob_name: str) -> pd.DataFrame:
    """
    Parse error log file from Azure Blob Storage and convert to structured DataFrame.

    Azure connection details are read from environment variables:
    - AZURE_STORAGE_CONNECTION_STRING: Azure storage account connection string
    - INPUT_CONTAINER_NAME: Container name in blob storage

    Args:
        blob_name: Name of the blob file in Azure storage (e.g., "error_logs.txt")

    Returns:
        DataFrame with columns: raw_text, date, time, error_code, error_msg, timestamp

    Raises:
        EnvironmentError: If required environment variables are not set
        Exception: If Azure blob access fails
    """
    # Load environment variables from .env file
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

    # Initialize data structure (we'll return only the three required columns)
    data = {
        "timestamp": [],
        "error_code": [],
        "description": [],
    }

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

        # Process each line from blob content, carrying forward last seen date
        last_date = None
        for line in blob_content.splitlines():
            text = line.strip()
            if not text:
                continue

            # Extract date and time
            date = extract_date(text)
            time = extract_time(text)

            # Update last_date if a full date is present
            if date:
                last_date = date.replace('/', '-')

            # Attempt to extract an error code (XXXX-###)
            error_code = extract_error_code(text)

            # Handle comma-separated code,message like `CODE,Message`
            comma_match = re.match(r'"?([A-Z]{4}-\d{3})[,\s]+(.+)"?$', text)
            if comma_match and not error_code:
                error_code = comma_match.group(1)
                description = comma_match.group(2)
            else:
                # Extract description by removing date/time/code tokens
                description = extract_error_message(text, date, time, error_code)

            # Determine effective date for timestamp (carry-forward last_date)
            effective_date = date.replace('/', '-') if date else None
            if time and not effective_date and last_date:
                effective_date = last_date

            # Build ISO timestamp if possible
            ts = extract_timestamp(effective_date, time)
            if ts:
                ts = ts.replace('/', '-')
            else:
                ts = 'missing'

            # Normalize error_code and description
            if not error_code:
                error_code = 'missing'

            description = description.strip() if description and description.strip() else 'missing'

            data["timestamp"].append(ts)
            data["error_code"].append(error_code)
            data["description"].append(description)

    except Exception as e:
        raise Exception(f"Failed to read from Azure Blob Storage: {e}") from e

    # Create DataFrame with exactly three columns in the requested order
    df = pd.DataFrame(data, columns=["timestamp", "error_code", "description"])
    return df


class ErrorLogsCleanup:
    """Service class to process `error_logs.txt` files from Azure Blob Storage.

    Usage:
        service = ErrorLogsCleanup()
        service.process_all_blobs()
        service.process_blob('error_logs.txt')
    """

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
        """Process a single blob (download, parse, upload cleaned CSV).

        Returns the output blob name on success.
        """
        # Download content
        blob_client = self.input_container_client.get_blob_client(blob_name)
        content = blob_client.download_blob().readall().decode("utf-8")

        # Parse lines into the three required columns (timestamp, error_code, description)
        data = {
            "timestamp": [],
            "error_code": [],
            "description": [],
        }

        last_date = None
        for raw in content.splitlines():
            text = raw.strip()
            if not text:
                continue

            date = extract_date(text)
            time = extract_time(text)

            if date:
                last_date = date.replace('/', '-')

            error_code = extract_error_code(text)

            comma_match = re.match(r'"?([A-Z]{4}-\d{3})[,\s]+(.+)"?$', text)
            if comma_match and not error_code:
                error_code = comma_match.group(1)
                description = comma_match.group(2)
            else:
                description = extract_error_message(text, date, time, error_code)

            effective_date = date.replace('/', '-') if date else None
            if time and not effective_date and last_date:
                effective_date = last_date

            ts = extract_timestamp(effective_date, time)
            ts = ts.replace('/', '-') if ts else 'missing'

            if not error_code:
                error_code = 'missing'

            description = description.strip() if description and description.strip() else 'missing'

            data['timestamp'].append(ts)
            data['error_code'].append(error_code)
            data['description'].append(description)

        df = pd.DataFrame(data, columns=["timestamp", "error_code", "description"])

        # Build output CSV bytes
        output_csv = df.to_csv(index=False)
        output_bytes = output_csv.encode("utf-8")

        # Upload to output container with .csv extension
        base = os.path.splitext(os.path.basename(blob_name))[0]
        output_name = f"{base}.csv"
        out_blob_client = self.output_container_client.get_blob_client(output_name)
        out_blob_client.upload_blob(output_bytes, overwrite=True)

        return output_name

    def process_all_blobs(self):
        """Process any `error_logs.txt` files found in the input container."""
        found = False
        for blob in self.input_container_client.list_blobs():
            if os.path.basename(blob.name).lower() == "error_logs.txt":
                found = True
                self.process_blob(blob.name)

        if not found:
            raise FileNotFoundError("No error_logs.txt files found in input container")


# Main execution
if __name__ == "__main__":
    # Example usage - Parse log file from Azure Blob Storage
    blob_name = "error_logs.txt"  # Name of the file in Azure Blob Storage

    try:
        # Parse the log file from Azure Blob Storage
        df = parse_error_log(blob_name)

        # Display the results
        print("DataFrame shape:", df.shape)
        print("\nFirst 10 rows:")
        print(df.head(10))

        print("\nDataFrame info:")
        print(df.info())

        print("\nSample of extracted data:")
        print(df[["timestamp", "error_code", "description"]].head(15))

        # Save to CSV (optional)
        output_file = "/mnt/user-data/outputs/parsed_error_logs.csv"
        df.to_csv(output_file, index=False)
        print(f"\nDataFrame saved to: {output_file}")

    except EnvironmentError as e:
        print(f"Environment configuration error: {e}")
        print("Please ensure your .env file contains:")
        print("AZURE_STORAGE_CONNECTION_STRING=your_connection_string")
        print("INPUT_CONTAINER_NAME=your_container_name")
    except Exception as e:
        print(f"Error processing log file: {e}")
