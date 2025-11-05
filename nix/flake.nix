{
  description = "NixOS configurations for Kubernetes cluster with keepalived VIP - NICO managed";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, disko }:
    let
      # Read cluster configuration (injected by NICO as additionalFile)
      # NICO will place this file in the working directory
      clusterConfig = if builtins.pathExists ./cluster.nix
        then import ./cluster.nix
        else {
          name = "default-cluster";
          vip = "192.168.1.100";
          controlPlane = [];
          workers = [];
        };

      # Create node configurations dynamically from cluster.nix
      nodeConfigurations = import ./nodes/generator.nix {
        inherit clusterConfig nixpkgs disko;
      };

      # Minimal configuration for cleanup (required by NICO)
      minimalConfig = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [
          disko.nixosModules.disko
          ./nodes/minimal.nix
        ];
      };

    in
    {
      # All node configurations from cluster.nix
      nixosConfigurations = nodeConfigurations // {
        # Required by NICO for cleanup
        minimal = minimalConfig;
      };

      # Development shell
      devShells.x86_64-linux = let
        pkgs = nixpkgs.legacyPackages.x86_64-linux;
      in pkgs.mkShell {
        buildInputs = with pkgs; [
          nixpkgs-fmt
          statix
          deadnix
        ];
      };
    };
}
