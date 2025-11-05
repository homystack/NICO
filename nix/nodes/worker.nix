{ config, pkgs, lib, clusterConfig, node, ... }:

let
  # Read join-token from NICO-injected file (in configurationSubdir root)
  joinTokenPath = ../join-token;
  hasJoinToken = builtins.pathExists joinTokenPath;

  # VIP from cluster config
  vip = clusterConfig.vip or "192.168.1.100";

in
{
  # K3s agent configuration for worker nodes
  services.k3s = {
    enable = true;
    role = "agent";

    # Connect to control plane via VIP
    serverAddr = "https://${vip}:6443";

    # Token file location (will be created from injected join-token)
    tokenFile = "/var/lib/rancher/k3s/agent/token";

    # K3s agent configuration
    extraFlags = toString [
      "--node-ip=${node.ip}"
    ];
  };

  # Ensure k3s starts after network is online
  systemd.services.k3s = {
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];

    # Wait for control plane VIP to be available
    serviceConfig = {
      ExecStartPre = [
        "${pkgs.coreutils}/bin/sleep 5"
        "${pkgs.bash}/bin/bash -c 'until ${pkgs.curl}/bin/curl -k https://${vip}:6443/ping; do ${pkgs.coreutils}/bin/sleep 2; done'"
      ];
    };
  };

  # Setup k3s token from NICO-injected file
  system.activationScripts.k3s-setup = lib.mkIf hasJoinToken {
    text = ''
      mkdir -p /var/lib/rancher/k3s/agent

      # Copy join token from injected file
      if [ -f ${joinTokenPath} ]; then
        cp ${joinTokenPath} /var/lib/rancher/k3s/agent/token
        chmod 600 /var/lib/rancher/k3s/agent/token
        echo "K3s token configured from NICO injection"
      fi
    '';
    deps = [];
  };

  # Firewall rules for worker nodes
  networking.firewall.allowedTCPPorts = [
    10250 # Kubelet metrics
    30000 # NodePort range start (adjust as needed)
  ];

  networking.firewall.allowedTCPPortRanges = [
    { from = 30000; to = 32767; } # NodePort services
  ];

  networking.firewall.allowedUDPPorts = [
    8472  # Flannel VXLAN
  ];

  # Additional packages for workers
  environment.systemPackages = with pkgs; [
    k3s
  ];

  # Ensure directories exist
  systemd.tmpfiles.rules = [
    "d /var/lib/rancher 0755 root root -"
    "d /var/lib/rancher/k3s 0755 root root -"
    "d /var/lib/rancher/k3s/agent 0755 root root -"
  ];

  # Logging configuration
  services.journald.extraConfig = ''
    SystemMaxUse=1G
    MaxRetentionSec=1week
  '';
}
