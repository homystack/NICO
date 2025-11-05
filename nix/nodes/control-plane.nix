{ config, pkgs, lib, clusterConfig, node, nodeIndex, totalControlPlaneNodes, ... }:

let
  # Read join-token from NICO-injected file (in configurationSubdir root)
  joinTokenPath = ../join-token;
  hasJoinToken = builtins.pathExists joinTokenPath;

  # First control plane node initializes, others join
  isFirstMaster = nodeIndex == 0;

  # VIP from cluster config
  vip = clusterConfig.vip or "192.168.1.100";

in
{
  # Keepalived configuration for VIP management
  services.keepalived = {
    enable = true;
    vrrpInstances.k8s_vip = {
      state = if isFirstMaster then "MASTER" else "BACKUP";
      interface = "eth0";
      virtualRouterId = 51;
      priority = 150 - nodeIndex; # First master has highest priority
      advert_int = 1;

      authentication = {
        auth_type = "PASS";
        auth_pass = builtins.substring 0 8 (builtins.hashString "sha256" clusterConfig.name);
      };

      virtual_ipaddress = [
        "${vip}/24"
      ];
    };
  };

  # K3s server configuration for control plane
  services.k3s = {
    enable = true;
    role = "server";

    # First master initializes, others join to VIP
    serverAddr = if isFirstMaster then "" else "https://${vip}:6443";

    # Token file location (will be created from injected join-token)
    tokenFile = "/var/lib/rancher/k3s/server/token";

    # K3s configuration
    extraFlags = toString ([
      "--node-ip=${node.ip}"
      "--advertise-address=${node.ip}"
      "--tls-san=${vip}"
      "--tls-san=${node.name}"
      "--tls-san=${node.ip}"
      "--disable=traefik" # Disable default traefik, can be installed via Helm
      "--write-kubeconfig-mode=644"
    ] ++ lib.optionals isFirstMaster [
      "--cluster-init" # Initialize embedded etcd cluster
    ]);
  };

  # Ensure k3s starts after keepalived
  systemd.services.k3s = {
    after = [ "keepalived.service" "network-online.target" ];
    wants = [ "keepalived.service" "network-online.target" ];

    # Add delay for non-first masters to wait for VIP to be available
    serviceConfig = lib.mkIf (!isFirstMaster) {
      ExecStartPre = [
        "${pkgs.coreutils}/bin/sleep 10"
        "${pkgs.bash}/bin/bash -c 'until ${pkgs.curl}/bin/curl -k https://${vip}:6443/ping; do ${pkgs.coreutils}/bin/sleep 2; done'"
      ];
    };
  };

  # Setup k3s token from NICO-injected file
  system.activationScripts.k3s-setup = lib.mkIf hasJoinToken {
    text = ''
      mkdir -p /var/lib/rancher/k3s/server

      # Copy join token from injected file
      if [ -f ${joinTokenPath} ]; then
        cp ${joinTokenPath} /var/lib/rancher/k3s/server/token
        chmod 600 /var/lib/rancher/k3s/server/token
        echo "K3s token configured from NICO injection"
      fi
    '';
    deps = [];
  };

  # Additional firewall rules for control plane
  networking.firewall.allowedTCPPorts = [
    6443  # Kubernetes API server
    2379  # etcd client
    2380  # etcd peer
    10250 # Kubelet metrics
    10251 # kube-scheduler (deprecated but still used)
    10252 # kube-controller-manager (deprecated but still used)
    10257 # kube-controller-manager secure
    10259 # kube-scheduler secure
  ];

  networking.firewall.allowedUDPPorts = [
    8472  # Flannel VXLAN
  ];

  # Logging configuration
  services.journald.extraConfig = ''
    SystemMaxUse=2G
    MaxRetentionSec=1week
  '';

  # Additional packages for control plane
  environment.systemPackages = with pkgs; [
    k3s
    kubectl
    kubernetes-helm
  ];

  # Ensure directories exist
  systemd.tmpfiles.rules = [
    "d /var/lib/rancher 0755 root root -"
    "d /var/lib/rancher/k3s 0755 root root -"
    "d /var/lib/rancher/k3s/server 0755 root root -"
  ];
}
