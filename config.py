import os
from dotenv import load_dotenv
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))

env_path = Path('.', '.env')
load_dotenv(dotenv_path=env_path)

class Config:
    # SECRET_KEY = os.getenv('SECRET_KEY')
    SECRET_KEY = 'key'
    SQLALCHEMY_DATABASE_URI = f'postgresql://postgres:m@localhost:5432/healthcheck'

    # SQLALCHEMY_DATABASE_URI = f'postgresql://{os.getenv("DB_USER")}:{os.getenv("DB_PASSWORD")}@{os.getenv("HOST_NAME")}:5432/{os.getenv("DB_NAME")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
    JWT_SECRET_KEY = 'secretjwtkey'