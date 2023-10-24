packer {
  required_plugins {
    amazon = {
      version = ">= 1.0.8"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-west-2"
  // default = "us-east-1"
}

variable "source_ami" {
  type    = string
  default = "ami-0b6edd8449255b799" # debian x86 us west 2
  // default = "ami-06db4d78cb1d3bbf9" # debian x86 us east 1
}

variable "subnet_id" {
  type    = string
  default = "subnet-00c72d88003ebe058" # us west 2
  // default = "subnet-0ef6e1dc73d995809" # us east 1
}

variable "ami_users" {
  type    = list(string)
  default = ["198085612719", "783925367808"]
}

variable "debian_version" {
  type    = string
  default = "12"
}

variable "ssh_username" {
  type    = string
  default = "admin"
}

variable "instance_type" {
  type    = string
  default = "t2.micro"
}

variable "app_name" {
  type    = string
  default = "webapp"
}

variable "db_name" {
  type    = string
  default = "healthcheck"
}

variable "aws_access_key" {
  type    = string
  default = env("AWS_ACCESS_KEY_ID")
}

variable "aws_secret_key" {
  type    = string
  default = env("AWS_SECRET_ACCESS_KEY")
}



source "amazon-ebs" "debian" {
  ami_name      = "ami-debian-${var.debian_version}-${formatdate("YYYY_MM_DD_hh_mm_ss", timestamp())}"
  instance_type = var.instance_type
  region        = var.aws_region
  subnet_id     = var.subnet_id


  aws_polling {
    delay_seconds = 60
    max_attempts  = 10

  }

  source_ami   = var.source_ami
  ami_users    = var.ami_users
  ssh_username = var.ssh_username

  access_key = var.aws_access_key
  secret_key = var.aws_secret_key

  launch_block_device_mappings {
    delete_on_termination = true
    device_name           = "/dev/sdf"
    volume_size           = 15
    volume_type           = "gp2"
  }
}

build {
  name    = "custom-ami"
  sources = ["source.amazon-ebs.debian"]



  provisioner "shell" {
    environment_vars = [
      "DEBIAN_VERSION=${var.debian_version}",
      "APP_NAME=${var.app_name}",
      "DB_NAME=${var.db_name}",
      "DEBIAN_FRONTEND=noninteractive",
      "CHECKPOINT_DISABLE=1"
    ]
    inline = [
      "sudo apt-get update",
      "sudo apt-get upgrade -y",
      "sudo apt-get install nginx -y",
      "sudo apt-get clean",
      "sudo apt install unzip -y",
      "sudo apt-get install -y python3 python3-pip postgresql postgresql-contrib",
      "sudo -u postgres psql -c \"ALTER USER postgres WITH PASSWORD 'm';\"",
      "sudo -u postgres psql -c \"CREATE DATABASE ${var.db_name};\""
    ]
  }

  provisioner "shell" {
    inline = [
      "echo 'Successfull run. ${var.app_name} is up and running'"
    ]
  }

  provisioner "file" {
    source      = "./webapp.zip"
    destination = "/tmp/webapp.zip"
  }

  provisioner "shell" {
    inline = [
      "sudo su - <<EOF",
      "mkdir -p /var/webapp",
      "unzip /tmp/webapp.zip -d /var/webapp",
      "cd /var/webapp",
      "sudo chmod -R 775 /var/webapp",
      "sudo apt update && sudo apt install python3.11-venv -y",
      "sudo apt update && sudo apt install  libpq-dev -y",
      "python3.11 -m venv env",
      "/bin/bash -c 'source /var/webapp/env/bin/activate'",
      "EOF"
    ]
  }


  provisioner "shell" {
    inline = [
      "echo 'Complete!!!!!!!!!!!!!!!!!'"
    ]
  }

  provisioner "shell" {
    inline = [
      "sudo su - <<EOF",
      "cd /var/webapp",
      "/bin/bash -c 'source env/bin/activate'",
      "env/bin/pip install --upgrade pip",
      "env/bin/pip install -r requirements.txt",
      "EOF"
    ]
  }

  # Setting up Gunicorn as a service
  provisioner "shell" {
    inline = [

      "sudo bash -c \"echo '[Unit]' > /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'Description=Gunicorn instance to serve Flask' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'After=network.target' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo '' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo '[Service]' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'User=root' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'Group=www-data' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'WorkingDirectory=/var/webapp' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'Environment=\"PATH=/var/webapp/env/bin\"' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'ExecStart=/var/webapp/env/bin/gunicorn --bind 0.0.0.0:8000 wsgi:app' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo '' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo '[Install]' >> /etc/systemd/system/app.service\"",
      "sudo bash -c \"echo 'WantedBy=multi-user.target' >> /etc/systemd/system/app.service\"",
      "sudo chown -R root:www-data /var/webapp",
      "sudo chmod -R 775 /var/webapp",
      "sudo systemctl daemon-reload",
      "sudo systemctl start app",
      "sudo systemctl enable app"

    ]
  }

  # Configuring Nginx
  provisioner "shell" {
    inline = [
      "sudo bash -c \"echo 'server {' > /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '    listen 80;' >> /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '' >> /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '    location / {' >> /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '        include proxy_params;' >> /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '        proxy_pass http://127.0.0.1:8000;' >> /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '    }' >> /etc/nginx/conf.d/app\"",
      "sudo bash -c \"echo '}' >> /etc/nginx/conf.d/app\"",
      "sudo systemctl reload nginx"
    ]
  }

  post-processor "manifest" {
    output     = "packer-manifest.json"
    strip_path = true
  }

}

