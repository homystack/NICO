{ clusterConfig, nixpkgs, disko }:

let
  # Common configuration for all nodes
  commonModule = { config, pkgs, lib, ... }: {
    imports = [
      ./common.nix
      disko.nixosModules.disko
    ];

    # Common networking and firewall
    networking.firewall.enable = true;
    networking.firewall.allowedTCPPorts = [ 22 ]; # SSH

    environment.systemPackages = with pkgs; [
      curl
      wget
      vim
      htop
      kubectl
    ];
  };

  # Control plane configuration generator
  mkControlPlaneNode = { node, nodeIndex, totalControlPlaneNodes }:
    nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      specialArgs = {
        inherit clusterConfig node nodeIndex totalControlPlaneNodes;
      };
      modules = [
        commonModule
        ./control-plane.nix
        ./disko-config.nix

        # Node-specific settings
        ({ config, pkgs, ... }: {
          networking.hostName = node.name;

          # Static IP configuration
          networking.useDHCP = false;
          networking.interfaces.eth0 = {
            useDHCP = false;
            ipv4.addresses = [{
              address = node.ip;
              prefixLength = 24;
            }];
          };

          # Default gateway (adjust as needed)
          networking.defaultGateway = {
            address = "192.168.1.1";
            interface = "eth0";
          };

          networking.nameservers = [ "8.8.8.8" "1.1.1.1" ];
        })
      ];
    };

  # Worker node configuration generator
  mkWorkerNode = { node }:
    nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      specialArgs = {
        inherit clusterConfig node;
      };
      modules = [
        commonModule
        ./worker.nix
        ./disko-config.nix

        # Node-specific settings
        ({ config, pkgs, ... }: {
          networking.hostName = node.name;

          # Static IP configuration
          networking.useDHCP = false;
          networking.interfaces.eth0 = {
            useDHCP = false;
            ipv4.addresses = [{
              address = node.ip;
              prefixLength = 24;
            }];
          };

          # Default gateway (adjust as needed)
          networking.defaultGateway = {
            address = "192.168.1.1";
            interface = "eth0";
          };

          networking.nameservers = [ "8.8.8.8" "1.1.1.1" ];
        })
      ];
    };

  # Generate control plane configurations
  controlPlaneNodes = clusterConfig.controlPlane or [];
  totalControlPlaneNodes = builtins.length controlPlaneNodes;

  controlPlaneConfigs = builtins.listToAttrs (
    builtins.genList (index:
      let
        node = builtins.elemAt controlPlaneNodes index;
      in {
        name = node.name;
        value = mkControlPlaneNode {
          inherit node;
          nodeIndex = index;
          inherit totalControlPlaneNodes;
        };
      }
    ) totalControlPlaneNodes
  );

  # Generate worker configurations
  workerNodes = clusterConfig.workers or [];
  workerConfigs = builtins.listToAttrs (
    map (node: {
      name = node.name;
      value = mkWorkerNode { inherit node; };
    }) workerNodes
  );

in
  # Merge control plane and worker configs
  controlPlaneConfigs // workerConfigs
