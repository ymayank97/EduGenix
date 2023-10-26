packer {
  required_plugins {
    amazon = {
      version = ">= 1.0.8"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "aws_region" {
  type = string
  // default = "us-west-2"
  default = "us-east-1"
}

variable "source_ami" {
  type = string
  // default = "ami-0b6edd8449255b799" # debian x86 us west 2
  default = "ami-06db4d78cb1d3bbf9" # debian x86 us east 1
}

variable "subnet_id" {
  type = string
  // default = "subnet-00c72d88003ebe058" # us west 2
  default = "subnet-0ef6e1dc73d995809" # us east 1
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

variable "app_dir" {
  type    = string
  default = "/opt/webapp"
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
      "DEBIAN_FRONTEND=noninteractive",
      "CHECKPOINT_DISABLE=1"
    ]
    inline = [
      "sudo apt-get update",
      "sudo apt-get upgrade -y",
      "sudo apt-get install nginx python3 python3-pip unzip -y",
      "sudo apt-get clean"
    ]
  }

  provisioner "file" {
    source      = "./webapp.zip"
    destination = "/tmp/webapp.zip"
  }

  provisioner "shell" {
    inline = [
      "sudo su -<<EOF",
      "adduser --disabled-password --gecos \"\" webapp_user",
      "mkdir -p ${var.app_dir}",
      "unzip /tmp/webapp.zip -d ${var.app_dir}",
      "chown -R webapp_user:webapp_user ${var.app_dir}",
      "cd ${var.app_dir}",
      "apt update && apt install python3.11-venv libpq-dev -y",
      "apt-get install cloud-init -y",
      "systemctl enable cloud-init",
      "python3.11 -m venv env",
      "source ${var.app_dir}/env/bin/activate",
      "env/bin/pip install --upgrade pip",
      "env/bin/pip install -r requirements.txt",
      "EOF"
    ]
  }


  # Setting up Gunicorn as a service
  provisioner "shell" {
    inline = [
      "sudo bash -c \"cat > /etc/systemd/system/app.service <<EOF",
      "[Unit]",
      "Description=Gunicorn instance to serve Flask",
      "After=network.target",
      "",
      "[Service]",
      "User=webapp_user",
      "Group=www-data",
      "WorkingDirectory=${var.app_dir}",
      "Environment=PATH=${var.app_dir}/env/bin",
      "ExecStart=${var.app_dir}/env/bin/gunicorn --bind 0.0.0.0:8000 wsgi:app",
      "Restart=on-failure",
      "RestartSec=1s",
      "",
      "[Install]",
      "WantedBy=multi-user.target",
    "EOF\"", ]
  }


  # Configuring Nginx
  provisioner "shell" {
    inline = [
      "sudo bash -c \"cat > /etc/nginx/conf.d/app <<EOF",
      "server {",
      "    listen 80;",
      "",
      "    location / {",
      "        include proxy_params;",
      "        proxy_pass http://127.0.0.1:8000;",
      "    }",
      "}",
    "EOF\"", ]
  }

  post-processor "manifest" {
    output     = "packer-manifest.json"
    strip_path = true
  }

}

