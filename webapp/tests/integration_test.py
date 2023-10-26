import pytest
from app import create_app, db
from config import Config
from app.models import User
from sqlalchemy import MetaData, create_engine
from sqlalchemy import MetaData, create_engine
import psycopg2

class TestConfig(Config):
    DB_USER = 'postgres'
    DB_PASSWORD = 'm'
    HOST_NAME = 'localhost'
    DB_NAME = 'healthcheck'
    JWT_SECRET_KEY = 'secret'
    SQLALCHEMY_DATABASE_URI = f'postgresql://{DB_USER}:{DB_PASSWORD}@{HOST_NAME}:5432/{DB_NAME}'

# Helper function to connect to PostgreSQL
def connect_to_postgres(dbname=None, user=None, password=None):
    conn = psycopg2.connect(
        host=TestConfig.HOST_NAME,
        port=5432,
        dbname=dbname or TestConfig.DB_NAME,
        user=user or TestConfig.DB_USER,
        password=password or TestConfig.DB_PASSWORD
    )
    return conn
    DB_USER = 'postgres'
    DB_PASSWORD = 'm'
    HOST_NAME = 'localhost'
    DB_NAME = 'healthcheck'
    JWT_SECRET_KEY = 'secret'
    SQLALCHEMY_DATABASE_URI = f'postgresql://{DB_USER}:{DB_PASSWORD}@{HOST_NAME}:5432/{DB_NAME}'

# Helper function to connect to PostgreSQL
def connect_to_postgres(dbname=None, user=None, password=None):
    conn = psycopg2.connect(
        host=TestConfig.HOST_NAME,
        port=5432,
        dbname=dbname or TestConfig.DB_NAME,
        user=user or TestConfig.DB_USER,
        password=password or TestConfig.DB_PASSWORD
    )
    return conn

@pytest.fixture
def client():
    app = create_app(TestConfig)
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_postgres_user_password():
    conn = connect_to_postgres(user="postgres", password="m")
    assert conn is not None
    conn.close()

def test_postgres_database():
    conn = connect_to_postgres(dbname="healthcheck")
    conn = connect_to_postgres(dbname="healthcheck")
    assert conn is not None
    conn.close()

def test_postgres_tables(client):
    engine = create_engine(TestConfig.SQLALCHEMY_DATABASE_URI)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    assert "user" in metadata.tables

def test_healthz_endpoint_success(client):
    response = client.get('/healthz')
    response = client.get('/healthz')
    assert response.status_code == 200

def test_healthz_endpoint_headers(client):
    response = client.get('/healthz')
    response = client.get('/healthz')
    assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
