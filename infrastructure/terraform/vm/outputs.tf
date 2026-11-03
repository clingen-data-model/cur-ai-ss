output "instance_name" {
  description = "Name of the compute instance"
  value       = google_compute_instance.this.name
}

output "instance_external_ip" {
  description = "External IP address of the instance"
  value       = google_compute_instance.this.network_interface[0].access_config[0].nat_ip
}

output "instance_internal_ip" {
  description = "Internal IP address of the instance"
  value       = google_compute_instance.this.network_interface[0].network_ip
}

output "standby_name" {
  description = "Name of the standby instance, if one is defined"
  value       = var.standby == null ? null : google_compute_instance.standby[0].name
}

output "service_account_email" {
  description = "Email of the service account"
  value       = google_service_account.this.email
}