terraform {
  required_version = ">= 1.5"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "4.0.0"
    }
  }
}

variable "group_id" { default = "g01" }
variable "image_name" { description = "Image tag, e.g. g01-helpdesk-triage:local" }
variable "docker_host" { default = "npipe:////./pipe/dockerDesktopLinuxEngine" }
variable "api_port" { default = 8001 }
variable "ui_port" { default = 8501 }
variable "llm_base_url" { default = "http://host.docker.internal:1234/v1" }
variable "llm_model" { default = "qwen/qwen2.5-vl-7b" }
variable "llm_timeout" { default = "60" }

provider "docker" { host = var.docker_host }

resource "docker_image" "app" {
  name         = var.image_name
  keep_locally = true
}

resource "docker_network" "net" { name = "${var.group_id}-net" }
resource "docker_volume" "data" { name = "${var.group_id}-data" }

resource "docker_container" "api" {
  name    = "${var.group_id}-api"
  image   = docker_image.app.image_id
  restart = "unless-stopped"
  env = [
    "LLM_PROVIDER=local",
    "SCENARIO_ID=g01",
    "LLM_BASE_URL=${var.llm_base_url}",
    "LLM_MODEL=${var.llm_model}",
    "LLM_TIMEOUT=${var.llm_timeout}",
    "DB_PATH=/data/analyses.db",
  ]
  networks_advanced { name = docker_network.net.name }
  ports {
    internal = 8000
    external = var.api_port
    ip       = "127.0.0.1"
  }
  volumes {
    volume_name    = docker_volume.data.name
    container_path = "/data"
  }
  host {
    host = "host.docker.internal"
    ip   = "host-gateway"
  }
}

resource "docker_container" "ui" {
  name    = "${var.group_id}-ui"
  image   = docker_image.app.image_id
  restart = "unless-stopped"
  command = ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0",
    "--server.port=8501", "--server.headless=true",
  "--browser.gatherUsageStats=false"]
  env = ["API_URL=http://${docker_container.api.name}:8000"]
  networks_advanced { name = docker_network.net.name }
  ports {
    internal = 8501
    external = var.ui_port
    ip       = "127.0.0.1"
  }
}

output "api_url" { value = "http://127.0.0.1:${var.api_port}" }
output "ui_url" { value = "http://127.0.0.1:${var.ui_port}" }
