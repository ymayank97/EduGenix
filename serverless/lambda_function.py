import json, base64, os, boto3, requests
from google.cloud import storage
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# Initialize Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS SES and DynamoDB clients
dynamodb = boto3.resource("dynamodb")


def lambda_handler(event, context):
    """
    Lambda function handler that processes an event triggered by an SNS message.

    Args:
        event (dict): The event data passed to the Lambda function.
        context (object): The runtime information of the Lambda function.

    Returns:
        dict: The response data returned by the Lambda function.
    """
    try:
        logger.info(f"Event received: {event}")

        # Check if 'Records' is present and has at least one record
        if "Records" in event and len(event["Records"]) > 0:
            # Try to parse the SNS message
            try:
                sns_message = json.loads(event["Records"][0]["Sns"]["Message"])

            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {str(e)}")
                logger.error(f"Raw message: {event['Records'][0]['Sns']['Message']}")
                return {"statusCode": 400, "body": "Invalid JSON format"}

            submission_url = sns_message.get("submission_url")
            recipient_email = sns_message.get("email")
            path = sns_message.get("Path")
            logger.info(f"path: {path}")

            if not submission_url or not recipient_email:
                raise ValueError(
                    "submission_url or email is missing in the SNS message"
                )

            # Download the release from GitHub
            response = requests.get(submission_url)
            if response.status_code != 200:
                raise Exception("Failed to download the release from GitHub.")

            logger.info(f"Downloaded the release from GitHub: {response.status_code}")

            # Initialize Google Cloud Storage client
            gcs_client = storage.Client.from_service_account_info(
                json.loads(os.environ["GCP_SERVICE_ACCOUNT_KEY"])
            )
            # Upload to Google Cloud Storage
            bucket_name = os.environ["BUCKET_NAME"]
            bucket = gcs_client.bucket(bucket_name)
            bucket_path = f"{path}/{os.path.basename(submission_url)}"
            blob = bucket.blob(bucket_path)
            blob.upload_from_string(response.content, content_type="application/zip")

            email_body_content = (
                "Hello, \n\n"
                + "Your submission number : "
                + str(path.split("/")[-1])
                + " for the assignment : "
                + str(path.split("/")[2])
                + " has been stored in the bucket : "
                + bucket_name
                + ".\n\n Path to the file: "
                + bucket_path
                + ".\n\n\n"
                + "Thank you!"
            )

            # Send email notification
            email_status = send_email_zoho(
                recipient_email, "Submission Received", email_body_content
            )

            # Update DynamoDB
            table = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
            table.put_item(
                Item={
                    "Id": context.aws_request_id,
                    "Email": recipient_email,
                    "Status": email_status,
                    "SubmissionUrl": submission_url,
                    "BucketName": bucket_name,
                    "EmailBodyContent": email_body_content,
                }
            )
            return {
                "statusCode": 200,
                "body": json.dumps("Process completed successfully."),
            }

        else:
            logger.error("No records found in the event")
            return {
                "statusCode": 400,
                "body": json.dumps("No records in the SNS event"),
            }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        send_email_zoho(
            recipient_email,
            "Submission Failed",
            "Your submission has failed. \n Error: " + str(e),
        )
        return {"statusCode": 500, "body": json.dumps(str(e))}


def send_email_zoho(recipient, subject, body):
    try:
        # Zoho Mail SMTP configuration
        smtp_server = "smtp.zoho.com"
        smtp_port = 587
        smtp_username = os.environ["ZOHO_MAIL"]  # Replace with your Zoho email
        smtp_password = os.environ[
            "ZOHO_PASSWORD"
        ]  # Replace with your Zoho email password

        # Create message
        msg = MIMEMultipart()
        msg["From"] = smtp_username
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Connect to Zoho Mail SMTP server
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)

            # Send email
            server.sendmail(smtp_username, recipient, msg.as_string())

        return "Sent"

    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return "Failed"


if __name__ == "__main__":
    lambda_handler(
        {
            "Records": [
                {
                    "Sns": {
                        "Message": '{"submission_url": "https://github.com/tparikh/myrepo/archive/refs/tags/v1.0.0.zip", "email": "sde.mayankyadav@gmail.com"}'
                    }
                }
            ]
        },
        None,
    )
