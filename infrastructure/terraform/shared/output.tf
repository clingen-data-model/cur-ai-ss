output "network" {
  description = "Default VPC network"
  value = {
    id         = google_compute_network.default.id
    name       = google_compute_network.default.name
    self_link  = google_compute_network.default.self_link
  }
}

output "subnetwork" {
  description = "Default subnetwork"
  value = {
    id            = google_compute_subnetwork.default.id
    name          = google_compute_subnetwork.default.name
    region        = google_compute_subnetwork.default.region
    ip_cidr_range = google_compute_subnetwork.default.ip_cidr_range
    self_link     = google_compute_subnetwork.default.self_link
  }
}
