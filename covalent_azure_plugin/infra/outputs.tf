output "name" {
  description = "The name of the Azure Resource Group"
  value       = local.resource_group.name
}

output "hostname" {
  description = "Fully qualified domain name of the A DNS record associated with the main node's public IP"
  value       = azurerm_public_ip.vm_public_ip[0].fqdn
}

output "hostnames" {
  description = "Fully qualified domain names of the A DNS record associated with the node's public IP"
  value       = [for pub_ip in azurerm_public_ip.vm_public_ip : pub_ip.fqdn]
}

output "private_ips" {
  description = "The Primary Private IP Addresses assigned to the nodes"
  value       = [for vm in azurerm_linux_virtual_machine.vm : vm.private_ip_address]
}

output "username" {
  description = "The username of the local administrator used for the Virtual Machine"
  value       = var.username
}

output "ssh_key" {
  description = "The username of the local administrator used for the Virtual Machine"
  value       = "${local.private_key_dir}/${local.private_key_name}"
}

output "env" {
  description = "Bash file to source to activate the environment"
  value       = local.env
}

output "python_path" {
  value       = "python3"
  description = "Python 3 path in the cloud instance"
}
