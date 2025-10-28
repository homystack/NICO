{ clusterConfig, nixpkgs }:

let
  # Common configuration for all nodes
  commonConfiguration = { config, pkgs, ... }: {
    imports = [
      ./common.nix
    ];

    # Common settings for all cluster nodes
    networking.firewall.allowedTCPPorts = [ 6443 2379 2380 10250 ];
    environment.systemPackages = with pkgs; [
      curl
      wget
      vim
    ];
  };

  # Control plane configuration with keepalived
  controlPlaneConfiguration = { config, pkgs, node, nodeIndex, totalControlPlaneNodes, ... }: {
    imports = [
      ./control-plane.nix
    ];

    # Node-specific settings
    networking.hostName = node.name;
    networking.interfaces.eth0.ipv4.addresses = [{
      address = node.ip;
      prefixLength = 24;
    }];

    # Pass parameters to control-plane module
    _module.args = {
      inherit node nodeIndex totalControlPlaneNodes;
    };
  };

  # Worker node configuration
  workerConfiguration = { config, pkgs, node, ... }: {
    imports = [
      ./worker.nix
    ];

    # Node-specific settings
    networking.hostName = node.name;
    networking.interfaces.eth0.ipv4.addresses = [{
      address = node.ip;
      prefixLength = 24;
    }];

    # Pass parameters to worker module
    _module.args = {
      inherit node;
    };
  };

  # Create node configurations
  controlPlaneNodes = clusterConfig.controlPlane;
  workerNodes = clusterConfig.workers;
  
  # Create control plane configurations
  controlPlaneConfigs = builtins.listToAttrs (builtins.genList (index: 
    let
      node = builtins.elemAt controlPlaneNodes index;
      nodeName = node.name;
    in
    {
      name = nodeName;
      value = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [
          commonConfiguration
          (controlPlaneConfiguration { 
            inherit node; 
            nodeIndex = index;
            totalControlPlaneNodes = builtins.length controlPlaneNodes;
          })
          (if builtins.pathExists ./${nodeName}/configuration.nix 
           then ./${nodeName}/configuration.nix 
           else {})
          (if builtins.pathExists ./${nodeName}/disko-config.nix 
           then ./${nodeName}/disko-config.nix 
           else ./default/disko-config.nix)
        ];
      };
    }
  ) (builtins.length controlPlaneNodes));

  # Create worker configurations
  workerConfigs = builtins.listToAttrs (builtins.genList (index: 
    let
      node = builtins.elemAt workerNodes index;
      nodeName = node.name;
    in
    {
      name = nodeName;
      value = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [
          commonConfiguration
          workerConfiguration
          (if builtins.pathExists ./${nodeName}/configuration.nix 
           then ./${nodeName}/configuration.nix 
           else {})
          (if builtins.pathExists ./${nodeName}/disko-config.nix 
           then ./${nodeName}/disko-config.nix 
           else ./default/disko-config.nix)
        ];
      };
    }
  ) (builtins.length workerNodes));

in controlPlaneConfigs // workerConfigs
