{ config, pkgs, lib, modulesPath, ... }:

let
  # Path to injected SSH private key from NICO (in configurationSubdir root)
  sshPrivateKeyPath = ../machine-ssh-private-key;

  # Check if SSH key was injected by NICO
  hasInjectedKey = builtins.pathExists sshPrivateKeyPath;

  # Read and generate public key from private key if it exists
  sshPublicKey = if hasInjectedKey
    then builtins.readFile (
      pkgs.runCommand "ssh-pubkey" {} ''
        ${pkgs.openssh}/bin/ssh-keygen -y -f ${sshPrivateKeyPath} > $out
      ''
    )
    else "";

in
{
  # Minimal NixOS configuration for cleanup after cluster deletion
  # This config is applied by NICO when a KubernetesCluster is deleted

  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./disko-config.nix
  ];

  # Boot configuration
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Basic networking
  networking.useDHCP = true;
  networking.firewall.enable = true;
  networking.firewall.allowedTCPPorts = [ 22 ];

  # Enable SSH for management
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      PermitRootLogin = "prohibit-password";
      PubkeyAuthentication = true;
    };
  };

  # Setup SSH keys from NICO-injected private key
  users.users.root = {
    openssh.authorizedKeys.keys = lib.optionals hasInjectedKey [ sshPublicKey ];
  };

  # Copy private key to root's SSH directory
  system.activationScripts.copySSHPrivateKey = lib.mkIf hasInjectedKey {
    text = ''
      mkdir -p /root/.ssh
      chmod 700 /root/.ssh

      # Copy injected private key
      cp ${sshPrivateKeyPath} /root/.ssh/id_ed25519
      chmod 600 /root/.ssh/id_ed25519

      # Generate public key
      ${pkgs.openssh}/bin/ssh-keygen -y -f /root/.ssh/id_ed25519 > /root/.ssh/id_ed25519.pub
      chmod 644 /root/.ssh/id_ed25519.pub
    '';
    deps = [];
  };

  # Minimal system packages
  environment.systemPackages = with pkgs; [
    vim
    htop
    curl
    wget
  ];

  # Enable nix flakes
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  # Stop and disable k3s services if they exist
  systemd.services = {
    k3s = {
      enable = false;
      wantedBy = lib.mkForce [];
    };
    k3s-server = {
      enable = false;
      wantedBy = lib.mkForce [];
    };
    k3s-agent = {
      enable = false;
      wantedBy = lib.mkForce [];
    };
    keepalived = {
      enable = false;
      wantedBy = lib.mkForce [];
    };
  };

  # Cleanup k3s data on activation
  system.activationScripts.cleanupK3s = {
    text = ''
      echo "Cleaning up k3s data..."

      # Stop k3s services if running
      systemctl stop k3s || true
      systemctl stop k3s-server || true
      systemctl stop k3s-agent || true
      systemctl stop keepalived || true

      # Remove k3s data
      rm -rf /var/lib/rancher/k3s || true
      rm -rf /etc/rancher || true

      # Remove k3s symlinks
      rm -f /usr/local/bin/kubectl || true
      rm -f /usr/local/bin/crictl || true
      rm -f /usr/local/bin/ctr || true

      # Clean container images (optional, saves space)
      # rm -rf /var/lib/k3s || true

      echo "K3s cleanup completed"
    '';
    deps = [];
  };

  # Time zone
  time.timeZone = "UTC";

  # System state version
  system.stateVersion = "24.05";
}
