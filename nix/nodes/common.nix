{ config, pkgs, lib, ... }:

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
  # Common system configuration for all cluster nodes
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Enable SSH
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      PermitRootLogin = "prohibit-password";
      PubkeyAuthentication = true;
    };
  };

  # Set timezone
  time.timeZone = "Europe/Moscow";

  # Setup SSH keys from NICO-injected private key
  users.users.root = {
    openssh.authorizedKeys.keys = lib.optionals hasInjectedKey [ sshPublicKey ];
  };

  # Copy private key to root's SSH directory for inter-node communication
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

  # System packages
  environment.systemPackages = with pkgs; [
    htop
    iotop
    iftop
    nload
    tmux
    git
    jq
    ncdu
    tree
  ];

  # Enable nix flakes
  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    auto-optimise-store = true;
  };

  # Garbage collection
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 7d";
  };

  # Kernel parameters for Kubernetes
  boot.kernel.sysctl = {
    "net.bridge.bridge-nf-call-iptables" = 1;
    "net.bridge.bridge-nf-call-ip6tables" = 1;
    "net.ipv4.ip_forward" = 1;
    "vm.swappiness" = 10;
    "fs.inotify.max_user_watches" = 524288;
    "fs.inotify.max_user_instances" = 512;
  };

  # Load required kernel modules
  boot.kernelModules = [ "br_netfilter" "overlay" ];

  # Disable swap (required for Kubernetes)
  swapDevices = lib.mkForce [];

  # Set system state version
  system.stateVersion = "24.05";
}
