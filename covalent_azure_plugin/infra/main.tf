# Copyright 2023 Agnostiq Inc.
#
# This file is part of Covalent.
#
# Licensed under the Apache License 2.0 (the "License"). A copy of the
# License may be obtained with this software package or at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Use of this file is prohibited except in compliance with the License.
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

provider "azapi" {
}

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}

resource "azurerm_resource_group" "vm" {
  name     = var.name
  location = var.location

  provisioner "local-exec" {
    command = "cd ~/.ssh && mkdir -p ${self.name}/ && chmod -R a-rwx,u+rwX ${self.name}/"
  }

  provisioner "local-exec" {
    command = "cd ~/.ssh && rm -r ${self.name}/"
    when    = destroy
  }
}

locals {
  env            = "~/.condaenvrc"
  resource_group = azurerm_resource_group.vm
  vms_count      = var.cluster_size
}

resource "azurerm_orchestrated_virtual_machine_scale_set" "cluster" {
  name                        = local.resource_group.name
  resource_group_name         = local.resource_group.name
  location                    = local.resource_group.location
  platform_fault_domain_count = 1
  instances                   = 0
}

resource "azurerm_linux_virtual_machine" "vm" {
  count                        = local.vms_count
  name                         = "${local.resource_group.name}-${count.index}"
  resource_group_name          = local.resource_group.name
  location                     = local.resource_group.location
  size                         = var.size
  admin_username               = var.username
  virtual_machine_scale_set_id = azurerm_orchestrated_virtual_machine_scale_set.cluster.id
  network_interface_ids = [
    azurerm_network_interface.vm_nic[count.index].id,
  ]

  computer_name = azurerm_public_ip.vm_public_ip[count.index].fqdn
  admin_ssh_key {
    username   = var.username
    public_key = tls_private_key.ssh_key.public_key_openssh
  }

  os_disk {
    name                 = "vm-disk-${count.index}"
    caching              = "ReadWrite"
    storage_account_type = var.storage_account_type
    disk_size_gb         = var.disk_size_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }
}

resource "azurerm_virtual_machine_extension" "vm" {
  count                = local.vms_count
  name                 = "NvidiaGpuDriverLinux"
  virtual_machine_id   = azurerm_linux_virtual_machine.vm[count.index].id
  publisher            = "Microsoft.HpcCompute"
  type                 = "NvidiaGpuDriverLinux"
  type_handler_version = "1.10"
}

resource "null_resource" "deps_install" {
  count = local.vms_count

  provisioner "file" {
    source      = "sudo-commands.sh"
    destination = "/tmp/script.sh"
  }

  provisioner "remote-exec" {
    inline = [
      "set -o errexit",
      "echo 'Installing Conda...'",
      "_CONDA_SH=Miniconda3-py310_22.11.1-1-Linux-x86_64.sh",
      "wget https://repo.anaconda.com/miniconda/$_CONDA_SH -O $_CONDA_SH",
      "chmod +x $_CONDA_SH",
      "! ./$_CONDA_SH -b -p ~/miniconda3",
      "echo 'Creating Conda Environment...'",
      "eval \"$(~/miniconda3/bin/conda shell.bash hook)\"",
      "echo 'eval \"$(~/miniconda3/bin/conda shell.bash hook)\"' >${local.env}",
      "conda init bash",
      "conda install virtualenv pip -y",
      "conda activate covalent || conda create -n covalent -y && conda activate covalent",
      "conda install python=${var.python3_version} virtualenv pip -y",
      "conda activate covalent",
      "echo 'Installing Covalent...'",

      "pip install \"covalent==${var.covalent_version}\"",
      "chmod +x /tmp/script.sh",
      "sudo bash /tmp/script.sh",
      "echo ok"
    ]
  }

  connection {
    type        = "ssh"
    user        = var.username
    private_key = file("${local.private_key_dir}/${local.private_key_name}")
    host        = azurerm_linux_virtual_machine.vm[count.index].public_ip_address
  }

  depends_on = [
    azurerm_virtual_machine_extension.vm
  ]
}
