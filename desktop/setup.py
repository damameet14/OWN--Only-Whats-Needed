"""First-run setup — configures hosts file and checks for models."""

import ctypes
import os
import platform
import sys
import subprocess

if getattr(sys, 'frozen', False):
    _PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP_MARKER = os.path.join(_PROJECT_ROOT, "data", ".setup_complete")


def is_first_run() -> bool:
    """Check if this is the first run (setup hasn't been completed)."""
    return not os.path.exists(SETUP_MARKER)


def mark_setup_complete():
    """Mark setup as complete."""
    os.makedirs(os.path.dirname(SETUP_MARKER), exist_ok=True)
    with open(SETUP_MARKER, "w") as f:
        f.write("ok\n")


def is_admin() -> bool:
    """Check if running with admin privileges."""
    if platform.system() == "Windows":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.getuid() == 0


def configure_hosts_file(hostname: str = "own.local", ip: str = "127.0.0.1") -> bool:
    """Add own.local to the hosts file (requires admin/root).

    Returns True if successfully configured, False otherwise.
    """
    if platform.system() == "Windows":
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    else:
        hosts_path = "/etc/hosts"

    entry = f"{ip}\t{hostname}"

    # Check if already configured
    try:
        with open(hosts_path, "r") as f:
            content = f.read()
            if hostname in content:
                return True  # Already configured
    except PermissionError:
        pass  # Need admin

    # Try to write
    try:
        with open(hosts_path, "a") as f:
            f.write(f"\n{entry}\n")
        return True
    except PermissionError:
        if platform.system() == "Windows":
            # Launch an elevated process to add the entry
            cmd = f'echo {entry} >> "{hosts_path}"'
            try:
                result = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", "cmd.exe", f"/c {cmd}", None, 0
                )
                return result > 32
            except Exception:
                return False
        else:
            # On Linux/Mac, try sudo
            try:
                subprocess.run(
                    ["sudo", "tee", "-a", hosts_path],
                    input=f"\n{entry}\n".encode(),
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                return True
            except Exception:
                return False


def check_models_installed() -> bool:
    """Check if any Whisper models are present in models_data."""
    models_dir = os.path.join(_PROJECT_ROOT, "models_data")
    if not os.path.isdir(models_dir):
        return False
    for entry in os.listdir(models_dir):
        if os.path.isdir(os.path.join(models_dir, entry)):
            return True
    return False


def run_first_time_setup() -> dict:
    """Run first-time setup checks and return status.

    Returns:
        dict with keys: hosts_configured, models_installed, setup_complete
    """
    result = {
        "hosts_configured": False,
        "models_installed": False,
        "setup_complete": False,
    }

    # Step 1: Configure hosts file
    print("[Setup] Checking hosts file for own.local...")
    result["hosts_configured"] = configure_hosts_file()
    if result["hosts_configured"]:
        print("[Setup] ✓ own.local is configured")
    else:
        print("[Setup] ⚠ Could not configure own.local (admin privileges may be needed)")
        print("[Setup]   You can access the app at http://localhost instead")

    # Step 2: Check for models
    print("[Setup] Checking for installed models...")
    result["models_installed"] = check_models_installed()
    if result["models_installed"]:
        print("[Setup] ✓ Models found")
    else:
        print("[Setup] ⚠ No models found. Download one through the Models tab or web UI.")

    # Mark as complete
    mark_setup_complete()
    result["setup_complete"] = True
    print("[Setup] ✓ Setup complete!")

    return result
