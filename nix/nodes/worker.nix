{ config, pkgs, node, ... }:

let
  clusterConfig = import ../../cluster.nix;
in
{
  # K3s agent configuration for worker nodes
  services.k3s = {
    enable = true;
    role = "agent";
    serverAddr = "https://${clusterConfig.vip}:6443";
    tokenFile = "/var/lib/k3s/token";
    
    # Additional settings
    extraFlags = let
      nodeIP = node.ip;
    in
      toString [
        "--node-ip=${nodeIP}"
      ];
  };

  # Create token file for k3s
  system.activationScripts.k3s-token = {
    text = ''
      mkdir -p /var/lib/k3s
      echo "${clusterConfig.clusterToken}" > /var/lib/k3s/token
      chmod 600 /var/lib/k3s/token
    '';
  };

  # Firewall rules for worker nodes
  networking.firewall.allowedTCPPorts = [
    10250 # Kubelet
    30000 # NodePort range start
    32767 # NodePort range end
  ];

  # Worker nodes don't need keepalived, but we ensure they have basic networking
  networking.interfaces.eth0.ipv4.addresses = [{
    address = node.ip;
    prefixLength = 24;
  }];

  # Worker-specific packages (optional)
  environment.systemPackages = with pkgs; [
    nvidia-container-toolkit # if you have GPUs
  ];
}
