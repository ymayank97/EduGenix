from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import os, sys, logging, json
from config import Config
from logging.handlers import RotatingFileHandler
from statsd import StatsClient
import boto3

# Retrieve SNS Topic ARN from environment variable
sns_topic_arn = Config.SNS_TOPIC_ARN
AWS_profile_name = Config.AWS_PROFILE_NAME
# Create an SNS client
session = boto3.Session()
sns_client = session.client("sns", region_name="us-east-1")

db = SQLAlchemy()
bcrypt = Bcrypt()


# Function to publish message to SNS
def publish_to_sns(submission_url, user_email, assignment_id, assignment_name, submission_attempt):
    """ Publishes a message to SNS topic with submission URL and user email"""
    sns_client.publish(
        TopicArn=sns_topic_arn,
        Message=json.dumps({
            "submission_url": submission_url,
            "email": user_email,
            'Path': f"{user_email}/{assignment_id}/{assignment_name}/{submission_attempt + 1}",
        }),
    )

# Function to setup logging
def setup_logging(level=logging.INFO):
    """ Set up logging for the application """
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Set up the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Set up a simple console logger as a fallback
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # For non-Windows environments, attempt to set up file logging
    if not sys.platform.startswith("win"):
        log_directory = "/var/log/flask"
        info_log_file = "info.log"
        error_log_file = "error.log"
        max_log_size = 10 * 1024 * 1024
        backup_count = 5

        # Attempt to create the log directory
        try:
            os.makedirs(
                log_directory, exist_ok=True
            )  # create the log directory if it doesn't exist
            # Setup handlers for file logging
            info_log_path = os.path.join(log_directory, info_log_file)
            info_handler = RotatingFileHandler(
                info_log_path, maxBytes=max_log_size, backupCount=backup_count
            )
            info_handler.setLevel(logging.INFO)
            info_handler.setFormatter(formatter)
            root_logger.addHandler(info_handler)

            error_log_path = os.path.join(log_directory, error_log_file)
            error_handler = RotatingFileHandler(
                error_log_path, maxBytes=max_log_size, backupCount=backup_count
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            root_logger.addHandler(error_handler)

        except PermissionError as e:
            print(f"Failed to create log directory '{log_directory}'. {e}")
        except OSError as e:
            print(f"Failed to create log directory '{log_directory}'. {e}")

    return root_logger


# Initialize the logger
logger = setup_logging()
if logger:
    logger.info("Logging setup complete.")
else:
    print("Failed to setup file-based logging, falling back to console logging.")

statsd = StatsClient(host="localhost", port=8125, prefix="webapp")
# End-of-file (EOF)