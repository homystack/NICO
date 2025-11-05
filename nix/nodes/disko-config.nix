{ lib, ... }:

{
  # Disk configuration with 10GB for system and rest for LVM
  disko.devices = {
    disk = {
      main = {
        type = "disk";
        device = "/dev/sda";
        content = {
          type = "gpt";
          partitions = {
            # BIOS boot partition for GRUB
            boot = {
              size = "1M";
              type = "EF02";
            };

            # EFI System Partition
            ESP = {
              size = "512M";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
                mountOptions = [ "defaults" "umask=0077" ];
              };
            };

            # Root partition - 10GB for system
            root = {
              size = "10G";
              content = {
                type = "filesystem";
                format = "ext4";
                mountpoint = "/";
                mountOptions = [ "defaults" "noatime" ];
              };
            };

            # Rest of disk for LVM
            lvm = {
              size = "100%";
              content = {
                type = "lvm_pv";
                vg = "vg0";
              };
            };
          };
        };
      };
    };

    # LVM volume group with all LVM partitions
    lvm_vg = {
      vg0 = {
        type = "lvm_vg";
        lvs = {
          # Thin pool for flexible storage
          thinpool = {
            size = "100%FREE";
            lvm_type = "thin-pool";
            content = {
              type = "none";
            };
          };
        };
      };
    };
  };

  # File system configuration
  fileSystems = {
    "/" = {
      device = "/dev/disk/by-label/nixos";
      fsType = "ext4";
      options = [ "noatime" ];
    };

    "/boot" = {
      device = "/dev/disk/by-label/boot";
      fsType = "vfat";
      options = [ "umask=0077" ];
    };
  };

  # Boot configuration
  boot = {
    loader = {
      systemd-boot.enable = true;
      efi.canTouchEfiVariables = true;
      grub = {
        enable = lib.mkForce false;
        efiSupport = true;
        device = "nodev";
      };
    };

    # Enable LVM support
    initrd.kernelModules = [ "dm-snapshot" ];
    kernelModules = [ "dm-thin-pool" ];
  };
}
