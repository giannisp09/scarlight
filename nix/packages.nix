# nix/packages.nix — Scarlight Agent package built with uv2nix
{ inputs, ... }:
{
  perSystem =
    { pkgs, inputs', ... }:
    let
      scarlightAgent = pkgs.callPackage ./scarlight.nix {
        inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
        npm-lockfile-fix = inputs'.npm-lockfile-fix.packages.default;
        # Only embed clean revs — dirtyRev doesn't represent any upstream
        # commit, so comparing it would always claim "update available".
        rev = inputs.self.rev or null;
      };
    in
    {
      packages = {
        default = scarlightAgent;
        tui = scarlightAgent.scarlightTui;
        web = scarlightAgent.scarlightWeb;

        fix-lockfiles = scarlightAgent.scarlightNpmLib.mkFixLockfiles {
          packages = [ scarlightAgent.scarlightTui scarlightAgent.scarlightWeb ];
        };
      };
    };
}
