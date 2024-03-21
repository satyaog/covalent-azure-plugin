# https://learn.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-terraform?tabs=azure-cli

locals {
  ssh_key          = "id_rsa.covalent.${random_pet.domain_name[0].id}"
  private_key_name = "${local.ssh_key}.pem"
  private_key_dir  = "~/.ssh/${local.resource_group.name}"
}

# Not secure but avoids weird error from
# `resource "azapi_resource" "ssh_public_key"` on github
# https://registry.terraform.io/providers/hashicorp/tls/latest/docs/resources/private_key
# │ Error: Failed to retrieve resource
# │ 
# │   with azapi_resource.ssh_public_key,
# │   on ssh.tf line 9, in resource "azapi_resource" "ssh_public_key":
# │    9: resource "azapi_resource" "ssh_public_key" {
# │ 
# │ checking for presence of existing Resource: (ResourceId
# │ "/subscriptions/***/resourceGroups/covalent-azure-task-a100-86850c_jefanine/providers/Microsoft.Compute/sshPublicKeys/id_rsa.covalent.fleetsailfish"
# │ / Api Version "2023-09-01"): ChainedTokenCredential authentication failed
# │ GET http://169.254.169.254/metadata/identity/oauth2/token
# │ --------------------------------------------------------------------------------
# │ RESPONSE 400 Bad Request
# │ --------------------------------------------------------------------------------
# │ {
# │   "error": "invalid_request",
# │   "error_description": "Identity not found"
# │ }
# │ --------------------------------------------------------------------------------

resource "tls_private_key" "ssh_key" {
  algorithm = "RSA"
  rsa_bits  = 4096

  provisioner "local-exec" {
    command = "cd ~/.ssh/${local.resource_group.name} && echo \"$KEY\" >$FILE && chmod a-rwx,u+rw $FILE"
    environment = {
      KEY  = tls_private_key.ssh_key.private_key_pem
      FILE = local.private_key_name
    }
  }
}

# resource "azapi_resource" "ssh_public_key" {
#   type      = "Microsoft.Compute/sshPublicKeys@2023-09-01"
#   name      = local.ssh_key
#   location  = local.resource_group.location
#   parent_id = local.resource_group.id
# }

# resource "azapi_resource_action" "ssh_public_key_gen" {
#   type        = "Microsoft.Compute/sshPublicKeys@2023-09-01"
#   resource_id = azapi_resource.ssh_public_key.id
#   action      = "generateKeyPair"
#   method      = "POST"

#   response_export_values = ["publicKey", "privateKey"]

#   provisioner "local-exec" {
#     command = "cd ~/.ssh/${local.resource_group.name} && echo \"$KEY\" >$FILE && chmod a-rwx,u+rw $FILE"
#     environment = {
#       KEY  = azapi_resource_action.ssh_public_key_gen.output.privateKey
#       FILE = local.private_key_name
#     }
#   }
# }
