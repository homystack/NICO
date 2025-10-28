{ config, pkgs, ... }:

{
  # Common system configuration for all cluster nodes
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Enable SSH
  services.openssh.enable = true;
  services.openssh.settings.PasswordAuthentication = false;
  services.openssh.settings.PermitRootLogin = "yes";

  # Set timezone
  time.timeZone = "Europe/Moscow";

  # Users
  users.users.root.openssh.authorizedKeys.keys = [
    # Add your SSH public keys here
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI..."
  ];

  # System packages
  environment.systemPackages = with pkgs; [
    htop
    iotop
    nload
    tmux
    git
  ];

  # Enable nix flakes
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  # Garbage collection
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 7d";
  };
}
