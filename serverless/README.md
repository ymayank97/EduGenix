# serverless

# Serverless

This repository contains a Python script that defines an AWS Lambda function handler. The function processes an event triggered by an SNS message.

## Dependencies

The script uses several Python libraries including `json`, `base64`, `os`, `boto3`, `requests`, `google.cloud.storage`, `logging`, `smtplib`, `email.mime.text`, and `email.mime.multipart`.

## Functionality

The `lambda_handler` function takes an event and a context as arguments. The event is expected to contain an SNS message with a `submission_url` and an `email`. The function performs several operations including parsing the SNS message, downloading a file, uploading the file to Google Cloud Storage, sending an email notification, and updating a DynamoDB table.

## Error Handling

The function has robust error handling. It logs errors and sends an email notification if any step fails.

## Running the Script

The script can be run directly. It calls the `lambda_handler` function with a hardcoded event and `None` as the context.

## Environment Variables

The script uses several environment variables:

- `GCP_SERVICE_ACCOUNT_KEY`: The service account key for Google Cloud Storage.
- `BUCKET_NAME`: The name of the Google Cloud Storage bucket.
- `DYNAMODB_TABLE`: The name of the DynamoDB table.
- `ZOHO_MAIL`: The Zoho email.
- `ZOHO_PASSWORD`: The Zoho email password.

Please ensure these environment variables are set before running the script.

## Note

This script is designed to be run in an AWS Lambda environment. If you're running it outside of AWS Lambda, you may need to modify it to suit your environment.