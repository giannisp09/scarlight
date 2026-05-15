"""Shared constants for Scarlight Agent.

Import-safe module with no dependencies — can be imported from anywhere
without risk of circular imports.
"""

import os
from pathlib import Path


_profile_fallback_warned: bool = False


def get_scarlight_home() -> Path:
    """Return the Scarlight home directory (default: ~/.scarlight).

    Reads SCARLIGHT_HOME env var, falls back to ~/.scarlight.
    This is the single source of truth — all other copies should import this.

    When ``SCARLIGHT_HOME`` is unset but an ``active_profile`` file indicates
    a non-default profile is active, logs a loud one-shot warning to
    ``errors.log`` so cross-profile data corruption is diagnosable instead
    of silent.  Behavior is unchanged otherwise — we still return
    ``~/.scarlight`` — because raising here would brick 30+ module-level
    callers that import this at load time.  Subprocess spawners are
    expected to propagate ``SCARLIGHT_HOME`` explicitly (see the systemd
    template in ``scarlight_cli/gateway.py`` and the kanban dispatcher in
    ``scarlight_cli/kanban_db.py``).  See https://github.com/NousResearch/hermes-agent/issues/18594.
    """
    val = os.environ.get("SCARLIGHT_HOME", "").strip()
    if val:
        return Path(val)

    # Guard: if a non-default profile is sticky-active, warn once that
    # the fallback to the default profile is almost certainly wrong.
    global _profile_fallback_warned
    if not _profile_fallback_warned:
        try:
            # Inline the default-root resolution from get_default_scarlight_root()
            # to stay import-safe (this function is called from module scope
            # in 30+ files; we cannot afford to trigger logging setup here).
            active_path = (Path.home() / ".scarlight" / "active_profile")
            active = active_path.read_text().strip() if active_path.exists() else ""
        except (UnicodeDecodeError, OSError):
            active = ""
        if active and active != "default":
            _profile_fallback_warned = True
            # Write directly to stderr.  We intentionally do NOT route this
            # through ``logging`` because (a) this function is called at
            # module-import time from 30+ sites, often before logging is
            # configured, and (b) root-logger propagation would double-emit
            # on consoles where a StreamHandler is already attached.
            import sys
            msg = (
                f"[SCARLIGHT_HOME fallback] SCARLIGHT_HOME is unset but active "
                f"profile is {active!r}. Falling back to ~/.scarlight, which "
                f"is the DEFAULT profile — not {active!r}. Any data this "
                f"process writes will land in the wrong profile. The "
                f"subprocess spawner should pass SCARLIGHT_HOME explicitly "
                f"(see issue #18594)."
            )
            try:
                sys.stderr.write(msg + "\n")
                sys.stderr.flush()
            except Exception:
                pass

    return Path.home() / ".scarlight"


def get_default_scarlight_root() -> Path:
    """Return the root Scarlight directory for profile-level operations.

    In standard deployments this is ``~/.scarlight``.

    In Docker or custom deployments where ``SCARLIGHT_HOME`` points outside
    ``~/.scarlight`` (e.g. ``/opt/data``), returns ``SCARLIGHT_HOME`` directly
    — that IS the root.

    In profile mode where ``SCARLIGHT_HOME`` is ``<root>/profiles/<name>``,
    returns ``<root>`` so that ``profile list`` can see all profiles.
    Works both for standard (``~/.scarlight/profiles/coder``) and Docker
    (``/opt/data/profiles/coder``) layouts.

    Import-safe — no dependencies beyond stdlib.
    """
    native_home = Path.home() / ".scarlight"
    env_home = os.environ.get("SCARLIGHT_HOME", "")
    if not env_home:
        return native_home
    env_path = Path(env_home)
    try:
        env_path.resolve().relative_to(native_home.resolve())
        # SCARLIGHT_HOME is under ~/.scarlight (normal or profile mode)
        return native_home
    except ValueError:
        pass

    # Docker / custom deployment.
    # Check if this is a profile path: <root>/profiles/<name>
    # If the immediate parent dir is named "profiles", the root is
    # the grandparent — this covers Docker profiles correctly.
    if env_path.parent.name == "profiles":
        return env_path.parent.parent

    # Not a profile path — SCARLIGHT_HOME itself is the root
    return env_path


def get_optional_skills_dir(default: Path | None = None) -> Path:
    """Return the optional-skills directory, honoring package-manager wrappers.

    Packaged installs may ship ``optional-skills`` outside the Python package
    tree and expose it via ``SCARLIGHT_OPTIONAL_SKILLS``.
    """
    override = os.getenv("SCARLIGHT_OPTIONAL_SKILLS", "").strip()
    if override:
        return Path(override)
    if default is not None:
        return default
    return get_scarlight_home() / "optional-skills"


def get_scarlight_dir(new_subpath: str, old_name: str) -> Path:
    """Resolve a Scarlight subdirectory with backward compatibility.

    New installs get the consolidated layout (e.g. ``cache/images``).
    Existing installs that already have the old path (e.g. ``image_cache``)
    keep using it — no migration required.

    Args:
        new_subpath: Preferred path relative to SCARLIGHT_HOME (e.g. ``"cache/images"``).
        old_name: Legacy path relative to SCARLIGHT_HOME (e.g. ``"image_cache"``).

    Returns:
        Absolute ``Path`` — old location if it exists on disk, otherwise the new one.
    """
    home = get_scarlight_home()
    old_path = home / old_name
    if old_path.exists():
        return old_path
    return home / new_subpath


def display_scarlight_home() -> str:
    """Return a user-friendly display string for the current SCARLIGHT_HOME.

    Uses ``~/`` shorthand for readability::

        default:  ``~/.scarlight``
        profile:  ``~/.scarlight/profiles/coder``
        custom:   ``/opt/scarlight-custom``

    Use this in **user-facing** print/log messages instead of hardcoding
    ``~/.scarlight``.  For code that needs a real ``Path``, use
    :func:`get_scarlight_home` instead.
    """
    home = get_scarlight_home()
    try:
        return "~/" + str(home.relative_to(Path.home()))
    except ValueError:
        return str(home)


def get_subprocess_home() -> str | None:
    """Return a per-profile HOME directory for subprocesses, or None.

    When ``{SCARLIGHT_HOME}/home/`` exists on disk, subprocesses should use it
    as ``HOME`` so system tools (git, ssh, gh, npm …) write their configs
    inside the Scarlight data directory instead of the OS-level ``/root`` or
    ``~/``.  This provides:

    * **Docker persistence** — tool configs land inside the persistent volume.
    * **Profile isolation** — each profile gets its own git identity, SSH
      keys, gh tokens, etc.

    The Python process's own ``os.environ["HOME"]`` and ``Path.home()`` are
    **never** modified — only subprocess environments should inject this value.
    Activation is directory-based: if the ``home/`` subdirectory doesn't
    exist, returns ``None`` and behavior is unchanged.
    """
    scarlight_home = os.getenv("SCARLIGHT_HOME")
    if not scarlight_home:
        return None
    profile_home = os.path.join(scarlight_home, "home")
    if os.path.isdir(profile_home):
        return profile_home
    return None


VALID_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


def parse_reasoning_effort(effort: str) -> dict | None:
    """Parse a reasoning effort level into a config dict.

    Valid levels: "none", "minimal", "low", "medium", "high", "xhigh".
    Returns None when the input is empty or unrecognized (caller uses default).
    Returns {"enabled": False} for "none".
    Returns {"enabled": True, "effort": <level>} for valid effort levels.
    """
    if not effort or not effort.strip():
        return None
    effort = effort.strip().lower()
    if effort == "none":
        return {"enabled": False}
    if effort in VALID_REASONING_EFFORTS:
        return {"enabled": True, "effort": effort}
    return None


def is_termux() -> bool:
    """Return True when running inside a Termux (Android) environment.

    Checks ``TERMUX_VERSION`` (set by Termux) or the Termux-specific
    ``PREFIX`` path.  Import-safe — no heavy deps.
    """
    prefix = os.getenv("PREFIX", "")
    return bool(os.getenv("TERMUX_VERSION") or "com.termux/files/usr" in prefix)


_wsl_detected: bool | None = None


def is_wsl() -> bool:
    """Return True when running inside WSL (Windows Subsystem for Linux).

    Checks ``/proc/version`` for the ``microsoft`` marker that both WSL1
    and WSL2 inject.  Result is cached for the process lifetime.
    Import-safe — no heavy deps.
    """
    global _wsl_detected
    if _wsl_detected is not None:
        return _wsl_detected
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            _wsl_detected = "microsoft" in f.read().lower()
    except Exception:
        _wsl_detected = False
    return _wsl_detected


_container_detected: bool | None = None


def is_container() -> bool:
    """Return True when running inside a Docker/Podman container.

    Checks ``/.dockerenv`` (Docker), ``/run/.containerenv`` (Podman),
    and ``/proc/1/cgroup`` for container runtime markers.  Result is
    cached for the process lifetime.  Import-safe — no heavy deps.
    """
    global _container_detected
    if _container_detected is not None:
        return _container_detected
    if os.path.exists("/.dockerenv"):
        _container_detected = True
        return True
    if os.path.exists("/run/.containerenv"):
        _container_detected = True
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as f:
            cgroup = f.read()
            if "docker" in cgroup or "podman" in cgroup or "/lxc/" in cgroup:
                _container_detected = True
                return True
    except OSError:
        pass
    _container_detected = False
    return False


# ─── Well-Known Paths ─────────────────────────────────────────────────────────


def get_config_path() -> Path:
    """Return the path to ``config.yaml`` under SCARLIGHT_HOME.

    Replaces the ``get_scarlight_home() / "config.yaml"`` pattern repeated
    in 7+ files (skill_utils.py, scarlight_logging.py, scarlight_time.py, etc.).
    """
    return get_scarlight_home() / "config.yaml"


def get_skills_dir() -> Path:
    """Return the path to the skills directory under SCARLIGHT_HOME."""
    return get_scarlight_home() / "skills"



def get_env_path() -> Path:
    """Return the path to the ``.env`` file under SCARLIGHT_HOME."""
    return get_scarlight_home() / ".env"


# ─── Network Preferences ─────────────────────────────────────────────────────


def apply_ipv4_preference(force: bool = False) -> None:
    """Monkey-patch ``socket.getaddrinfo`` to prefer IPv4 connections.

    On servers with broken or unreachable IPv6, Python tries AAAA records
    first and hangs for the full TCP timeout before falling back to IPv4.
    This affects httpx, requests, urllib, the OpenAI SDK — everything that
    uses ``socket.getaddrinfo``.

    When *force* is True, patches ``getaddrinfo`` so that calls with
    ``family=AF_UNSPEC`` (the default) resolve as ``AF_INET`` instead,
    skipping IPv6 entirely.  If no A record exists, falls back to the
    original unfiltered resolution so pure-IPv6 hosts still work.

    Safe to call multiple times — only patches once.
    Set ``network.force_ipv4: true`` in ``config.yaml`` to enable.
    """
    if not force:
        return

    import socket

    # Guard against double-patching
    if getattr(socket.getaddrinfo, "_scarlight_ipv4_patched", False):
        return

    _original_getaddrinfo = socket.getaddrinfo

    def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == 0:  # AF_UNSPEC — caller didn't request a specific family
            try:
                return _original_getaddrinfo(
                    host, port, socket.AF_INET, type, proto, flags
                )
            except socket.gaierror:
                # No A record — fall back to full resolution (pure-IPv6 hosts)
                return _original_getaddrinfo(host, port, family, type, proto, flags)
        return _original_getaddrinfo(host, port, family, type, proto, flags)

    _ipv4_getaddrinfo._scarlight_ipv4_patched = True  # type: ignore[attr-defined]
    socket.getaddrinfo = _ipv4_getaddrinfo  # type: ignore[assignment]


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"

AI_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"

# Default terminal-sandbox container image. Used by every container backend
# (docker, singularity, modal, daytona) when the user picks one in
# `terminal.backend` and does not override `*_image` in cli-config.yaml.
#
# Why Kali: Scarlight's domain is offensive security; the agent's terminal
# tool is the dispatch surface for offensive binaries (nmap, gobuster,
# sqlmap, …).  The upstream hermes-agent default was a coding-oriented
# python+nodejs image, which is the wrong substrate for this product.
#
# Why `kali-last-release` minimal: kali official Docker images are minimal
# by design (~120MB).  Tools install on first use via `apt install -y
# <tool>` — kept minimal so first-pull is fast and skill files declare
# what they need (see skills/offensive/*/SKILL.md `prerequisites.commands`).
# A `-large` / `-headless` tools-included variant does not exist on the
# official registry.
#
# Why digest-pinned: reproducibility.  Bumping requires re-resolving the
# manifest-list digest (`docker buildx imagetools inspect <ref>` — NOT
# `docker manifest inspect`, which only shows per-arch entries), then
# updating this constant.
DEFAULT_TERMINAL_IMAGE = (
    "kalilinux/kali-last-release"
    "@sha256:59a4bea68a92b8e2f7b2490345a49784eb11264ceb7deece037e543b2a7dfd73"
)
