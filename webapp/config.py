import os
from dotenv import load_dotenv
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))

# Check if we are running on GitHub Actions
ON_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"

# Load .env file if we are not on GitHub and .env exists
if not ON_GITHUB:
    env_path = Path(basedir, '.env')
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'key')  # Default value is 'key'
    
    DB_USER = os.getenv("DATABASE_USER")
    DB_PASSWORD = os.getenv("DATABASE_PASSWORD")
    HOST_NAME = os.getenv("DATABASE_HOST")
    DB_NAME = os.getenv("DATABASE_NAME")
    
    SQLALCHEMY_DATABASE_URI = f'postgresql://{DB_USER}:{DB_PASSWORD}@{HOST_NAME}:5432/{DB_NAME}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False