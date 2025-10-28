{ config, pkgs, node, nodeIndex, totalControlPlaneNodes, ... }:

let
  clusterConfig = import ../../cluster.nix;
in
{
  # Keepalived configuration for VIP management
  services.keepalived = {
    enable = true;
    vrrpInstances."k8s_vip" = {
      state = if nodeIndex == 0 then "MASTER" else "BACKUP";
      interface = "eth0"; # Adjust interface as needed
      virtualRouterId = 51;
      priority = 150 - nodeIndex; # Higher priority for lower index (MASTER has highest)
      advertInt = 1;
      authentication = {
        authType = "PASS";
        authPass = "k8s_secret"; # In production, use a secure password
      };
      virtualIpaddress = [ "${clusterConfig.vip}/24" ];
    };
  };

  # K3s server configuration for control plane
  services.k3s = {
    enable = true;
    role = "server";
    
    # For the first control plane node, initialize the cluster
    # For others, join via VIP
    serverAddr = if nodeIndex == 0 then "" else "https://${clusterConfig.vip}:6443";
    tokenFile = "/var/lib/k3s/token";
    
    # Additional settings for HA
    extraFlags = let
      nodeIP = node.ip;
    in
      toString [
        "--node-ip=${nodeIP}"
        "--advertise-address=${nodeIP}"
        "--tls-san=${clusterConfig.vip}"
        "--cluster-init"  # Only for the first node, but k3s handles this
      ];
  };

  # Ensure k3s starts after keepalived
  systemd.services.k3s = {
    after = [ "keepalived.service" ];
    requires = [ "keepalived.service" ];
  };

  # Create token file for k3s (in production, this should be a secret)
  system.activationScripts.k3s-token = {
    text = ''
      mkdir -p /var/lib/k3s
      echo "${clusterConfig.clusterToken}" > /var/lib/k3s/token
      chmod 600 /var/lib/k3s/token
    '';
  };

  # Additional firewall rules for control plane
  networking.firewall.allowedTCPPorts = [
    6443  # Kubernetes API
    2379  # etcd client
    2380  # etcd peer
    10250 # Kubelet
    10259 # kube-scheduler
    10257 # kube-controller-manager
  ];

  # Monitoring and logging
  services.journald.extraConfig = ''
    SystemMaxUse=1G
  '';
}
