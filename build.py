import os
import subprocess
import sys
import shutil


def run_nuitka():
    print("🚀 Starting Nuitka Build Process...")

    # Define the Nuitka command
    command = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--windows-disable-console",

        # ── Icon ──────────────────────────────────────────────────────────
        "--windows-icon-from-ico=logo.ico",

        # ── Project sub-packages (Nuitka needs explicit includes for
        #    packages that are only imported dynamically or via strings) ──
        "--include-package=server",
        "--include-package=core",
        "--include-package=desktop",
        "--include-package=models",

        # ── Third-party packages with dynamic/lazy imports ────────────────
        "--include-package=faster_whisper",
        "--include-package=ctranslate2",
        "--include-package=vosk",
        "--include-package=tqdm",
        "--include-package=huggingface_hub",
        "--include-package=indic_transliteration",
        "--include-package=llama_cpp",
        "--include-package=aiofiles",
        "--include-package=websockets",
        "--include-package=uvicorn",
        "--include-package=fastapi",
        "--include-package=starlette",
        "--include-package=pystray",
        "--include-package=customtkinter",
        "--include-package=win10toast",
        "--include-package=playwright",

        # ── Data directories to bundle ────────────────────────────────────
        "--include-data-dir=web=web",
        "--include-data-dir=fonts=fonts",
        # NOTE: bin/ contains .exe files (ffmpeg, ffprobe) which Nuitka's
        # --include-data-dir intentionally skips. They are copied post-build.

        # ── Individual data files ─────────────────────────────────────────
        "--include-data-files=logo.ico=logo.ico",
        "--include-data-files=logo.png=logo.png",

        # ── Nuitka plugins ────────────────────────────────────────────────
        "--enable-plugin=tk-inter",
        "--include-package-data=customtkinter",
    ]

    # Add resources folder if it exists
    if os.path.exists("resources"):
        command.append("--include-data-dir=resources=resources")

    # Entry point
    command.append("main.py")

    print("Running command:")
    print("  " + " ".join(command))
    print()

    try:
        subprocess.run(command, check=True)
        print()
        print("✅ Nuitka build completed successfully!")
        print("The bundled application is in 'main.dist/' folder.")
        print()
        _post_build_checks()
    except subprocess.CalledProcessError as e:
        print(f"❌ Nuitka build failed with error code {e.returncode}")


def _post_build_checks():
    """Copy excluded files and verify the build output."""
    dist_dir = "main.dist"

    # ── Copy bin/ executables (Nuitka skips .exe from --include-data-dir) ──
    src_bin = "bin"
    dst_bin = os.path.join(dist_dir, "bin")
    if os.path.isdir(src_bin):
        os.makedirs(dst_bin, exist_ok=True)
        for fname in os.listdir(src_bin):
            src_file = os.path.join(src_bin, fname)
            dst_file = os.path.join(dst_bin, fname)
            if os.path.isfile(src_file) and not os.path.exists(dst_file):
                print(f"  Copying {fname} -> {dst_bin}/")
                shutil.copy2(src_file, dst_file)

    checks = {
        "web/index.html": "Web frontend",
        "web/editor.html": "Editor page",
        "web/export_render.html": "Export render template",
        "bin/ffmpeg.exe": "FFmpeg binary",
        "bin/ffprobe.exe": "FFprobe binary",
        "fonts": "Fonts directory",
        "logo.ico": "Application icon",
    }

    print("-- Post-build checks --")
    all_ok = True
    for rel_path, description in checks.items():
        full = os.path.join(dist_dir, rel_path)
        exists = os.path.exists(full)
        status = "[OK]" if exists else "[MISSING]"
        print(f"  {status}  {description} ({rel_path})")
        if not exists:
            all_ok = False

    if os.path.exists(os.path.join(dist_dir, "resources", "presets.json")):
        print("  [OK]  Presets file (resources/presets.json)")
    else:
        print("  [MISSING]  Presets file (resources/presets.json)")
        all_ok = False

    # Create empty runtime directories inside dist
    for d in ["data", "data/uploads", "data/thumbnails", "data/exports", "models_data"]:
        dp = os.path.join(dist_dir, d)
        os.makedirs(dp, exist_ok=True)
    print("  [OK]  Created runtime directories (data/, models_data/)")

    if all_ok:
        print("\nAll post-build checks passed!")
    else:
        print("\nWARNING: Some checks failed - review the output above.")


if __name__ == "__main__":
    # Pre-flight checks
    if not os.path.exists("logo.ico"):
        print("WARNING: logo.ico not found. The installer will not have a custom icon.")

    if not os.path.exists("bin/ffmpeg.exe") or not os.path.exists("bin/ffprobe.exe"):
        print("WARNING: ffmpeg.exe or ffprobe.exe not found in bin/ folder.")
        print("   Video processing features will fail in the bundled app.")

    run_nuitka()
