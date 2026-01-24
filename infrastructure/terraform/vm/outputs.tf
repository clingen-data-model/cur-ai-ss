output "instance_name" {
  description = "Name of the compute instance"
  value       = google_compute_instance.caa_dashboard.name
}

output "instance_external_ip" {
  description = "External IP address of the instance"
  value       = google_compute_instance.caa_dashboard.network_interface[0].access_config[0].nat_ip
}

output "instance_internal_ip" {
  description = "Internal IP address of the instance"
  value       = google_compute_instance.caa_dashboard.network_interface[0].network_ip
}

output "service_account_email" {
  description = "Email of the service account"
  value       = google_service_account.caa_dashboard.email
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "gcloud compute ssh caa-dashboard --zone=us-east4-a --project=clingen-caa"
}
