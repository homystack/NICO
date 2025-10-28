{
  description = "NixOS configurations for Kubernetes cluster with keepalived VIP";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      # Read cluster configuration
      clusterConfig = import ./cluster.nix;

      # Create node configurations
      nodeConfigurations = import ./nodes/default.nix { 
        inherit clusterConfig nixpkgs; 
      };

    in
    {
      nixosConfigurations = nodeConfigurations;

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
