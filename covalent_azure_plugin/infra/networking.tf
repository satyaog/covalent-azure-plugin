# https://learn.microsoft.com/en-us/azure/virtual-machines/linux/quick-create-terraform?tabs=azure-cli

resource "random_pet" "domain_name" {
  count     = local.vms_count
  separator = ""
}

# Create virtual network
resource "azurerm_virtual_network" "vm_network" {
  name                = "vm-network"
  address_space       = ["10.0.0.0/16"]
  location            = local.resource_group.location
  resource_group_name = local.resource_group.name
}

# Create subnet
resource "azurerm_subnet" "vm_subnet" {
  name                 = "internal"
  resource_group_name  = local.resource_group.name
  virtual_network_name = azurerm_virtual_network.vm_network.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Create public IPs
resource "azurerm_public_ip" "vm_public_ip" {
  count               = local.vms_count
  name                = "vm-public-ip-${count.index}"
  location            = local.resource_group.location
  resource_group_name = local.resource_group.name
  domain_name_label   = random_pet.domain_name[count.index].id
  allocation_method   = "Dynamic"
}

# Create Network Security Group and rule
resource "azurerm_network_security_group" "vm_nsg" {
  count               = local.vms_count
  name                = "vm-network-security-group-${count.index}"
  location            = local.resource_group.location
  resource_group_name = local.resource_group.name

  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

# Create network interface
resource "azurerm_network_interface" "vm_nic" {
  count               = local.vms_count
  name                = "vm-nic-${count.index}"
  location            = local.resource_group.location
  resource_group_name = local.resource_group.name

  ip_configuration {
    name                          = "internal-${count.index}"
    subnet_id                     = azurerm_subnet.vm_subnet.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.vm_public_ip[count.index].id
  }
}

# Connect the security group to the network interface
resource "azurerm_network_interface_security_group_association" "vm" {
  count                     = local.vms_count
  network_interface_id      = azurerm_network_interface.vm_nic[count.index].id
  network_security_group_id = azurerm_network_security_group.vm_nsg[count.index].id
}
