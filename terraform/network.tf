# VPC Network
resource "google_compute_network" "default" {
  name                    = "default"
  auto_create_subnetworks = false
}

# Subnet
resource "google_compute_subnetwork" "default" {
  name                     = "default-subnet"
  ip_cidr_range            = "10.0.0.0/24"
  region                   = "us-east4"
  network                  = google_compute_network.default.id
  private_ip_google_access = false
  stack_type               = "IPV4_ONLY"
}

# Firewall rule - Allow internal traffic within subnet
resource "google_compute_firewall" "allow_custom" {
  name        = "default-allow-custom"
  network     = google_compute_network.default.name
  description = "Allows connection from any source to any instance on the network using custom protocols."
  priority    = 65534

  allow {
    protocol = "all"
  }

  source_ranges = ["10.0.0.0/24"]
}

# Firewall rule - Allow ICMP
resource "google_compute_firewall" "allow_icmp" {
  name        = "default-allow-icmp"
  network     = google_compute_network.default.name
  description = "Allows ICMP connections from any source to any instance on the network."
  priority    = 65534

  allow {
    protocol = "icmp"
  }

  source_ranges = ["0.0.0.0/0"]
}

# Firewall rule - Allow SSH
resource "google_compute_firewall" "allow_ssh" {
  name        = "default-allow-ssh"
  network     = google_compute_network.default.name
  description = "Allows TCP connections from any source to any instance on the network using port 22."
  priority    = 65534

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["allow-ssh"]
}

# Firewall rule - Allow HTTP
resource "google_compute_firewall" "allow_http" {
  name     = "default-allow-http"
  network  = google_compute_network.default.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["80"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["http-server"]
}

# Firewall rule - Allow HTTPS
resource "google_compute_firewall" "allow_https" {
  name     = "default-allow-https"
  network  = google_compute_network.default.name
  priority = 1000

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["https-server"]
}

# Firewall rule - Allow GCP Health Checks (IPv4)
resource "google_compute_firewall" "allow_health_check" {
  name     = "default-allow-health-check"
  network  = google_compute_network.default.name
  priority = 1000

  allow {
    protocol = "tcp"
  }

  source_ranges = [
    "35.191.0.0/16",
    "130.211.0.0/22",
    "209.85.152.0/22",
    "209.85.204.0/22"
  ]
  target_tags = ["lb-health-check"]
}

# Firewall rule - Allow GCP Health Checks (IPv6)
resource "google_compute_firewall" "allow_health_check_ipv6" {
  name     = "default-allow-health-check-ipv6"
  network  = google_compute_network.default.name
  priority = 1000

  allow {
    protocol = "tcp"
  }

  source_ranges = [
    "2600:1901:8001::/48",
    "2600:2d00:1:b029::/64"
  ]
  target_tags = ["lb-health-check"]
}
