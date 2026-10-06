# Infrastructure task

Use the kreuzwerker/docker provider pinned to 4.0.0. Define one local image reference, one group network, one named SQLite volume and two containers from the same image. API ports are 8000 + group number and UI ports are 8500 + group number. Terraform exclusively owns these application resources. Commit the generated provider lock file, not state or tokens. Follow your group brief for variables and checks.
