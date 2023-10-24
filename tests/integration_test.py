import pytest

from app import create_app, db
from config import Config
from app.models import User
from sqlalchemy import MetaData
import psycopg2
from sqlalchemy import create_engine


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:postgres@localhost:5432/postgres'  # Adjust the URI as needed



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
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="postgres"
    )
    assert conn is not None
    conn.close()


def test_postgres_database():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="postgres",
        user="postgres",
        password="postgres"
    )
    assert conn is not None
    conn.close()


def test_postgres_tables(client):
    engine = create_engine(TestConfig.SQLALCHEMY_DATABASE_URI)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    assert "user" in metadata.tables


def test_healthz_endpoint_success(client):
    response = client.get('/api/healthz')
    assert response.status_code == 200


def test_healthz_endpoint_headers(client):
    response = client.get('/api/healthz')
    assert response.headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert response.headers["X-Content-Type-Options"] == "nosniff"



