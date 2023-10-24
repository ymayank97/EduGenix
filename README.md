# webapp


**Web Application**

This repository contains the source code for a Flask-based web application.

**Prerequisites**

Before you begin, ensure you have met the following requirements:

- Python: Ensure you have Python version 3.10 (or higher) installed. You can check your Python version with the command `python --version`.
- PostgreSQL: This application uses a PostgreSQL database. Make sure you have it installed and running. Additionally, set up the necessary environment variables or configurations for the database connection.
- pip: Ensure you have pip installed. This is the package installer for Python. You can check with the command `pip --version`.
- Virtual Environment: It's recommended to use a virtual environment for Python projects. You can use virtualenv or the built-in venv module in Python.
- Flask CLI: This is used for database migrations and running the app. Install it with `pip install Flask`.

**Build and Deploy Locally**

Step 1: Clone the Repository

```bash
git clone https://github.com/ymayank97/webapp.git
cd webapp
```

Step 2: Set Up a Virtual Environment

Using venv:

```bash
python -m venv env
source env/bin/activate  # On Windows, use `env\Scripts\activate`
```

Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

Step 4: Database Migrations

Before running the app, you need to apply the database migrations:

```bash
flask db upgrade
```

Step 5: Run the Application

```bash
flask run
```

The application should now be running at http://127.0.0.1:5000/.

**Deploy to Debian**



### Install Nginx

```bash
sudo apt install nginx
```

### Create a WSGI file

Create a file named `wsgi.py` and add the following code:

```python
from flaskapp import create_app

app = create_app()
if __name__ == "__main__":
   app.run()
```

### Start Gunicorn

Start Gunicorn with the following command:

```bash
gunicorn --bind 0.0.0.0:8001 wsgi:app -w 3
```

### Create a systemd service

Create a file named `app.service` in `/etc/systemd/system/` and add the following code:

```ini
[Unit]
Description=Gunicorn instance to serve Flask
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=/root/assignment3/webapp
Environment="PATH=/root/assignment3/webapp/env/bin"
ExecStart=/root/assignment3/webapp/env/bin/gunicorn --bind 0.0.0.0:8000 wsgi:app

[Install]
WantedBy=multi-user.target
```

### Set file permissions

Set the file permissions with the following commands:

```bash
chown -R root:www-data /root/assignment3/webapp
chmod -R 775 /root/assignment3/webapp
```

### Reload systemd daemon

Reload the systemd daemon with the following command:

```bash
systemctl daemon-reload
```

### Start and enable the service

Start the Flask service and enable it to start at system reboot with the following commands:

```bash
systemctl start app
systemctl enable app
```

### Verify the status of the service

Verify the status of the Flask service with the following command:

```bash
systemctl status app
```

### Configure Nginx

Create a file named `app` in `/etc/nginx/conf.d/` and add the following code:

```nginx
server {
    listen 80;

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:8000;
    }
}
```

### Reload Nginx

Reload Nginx with the following command:

```bash
sudo systemctl reload nginx
```

### Check error logs

Check the error logs for Gunicorn with the following command:

```bash
sudo journalctl -u app.service

```

