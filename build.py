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
        "--enable-plugin=pyside6",
        "--enable-plugin=tk-inter",
        "--include-package-data=customtkinter",
        "--include-data-dir=web=web",
        "--include-data-dir=fonts=fonts",
        "--include-data-dir=bin=bin",
        # Assuming resources folder might not exist yet, we only include it if it exists
    ]
    
    # Add resources folder if it exists
    if os.path.exists("resources"):
        command.append("--include-data-dir=resources=resources")
        
    # Optional: If the user provides an icon named "app_icon.ico", use it
    if os.path.exists("app_icon.ico"):
        command.append("--windows-icon-from-ico=app_icon.ico")
        
    # Entry point
    command.append("main.py")
    
    print("Running command:", " ".join(command))
    
    try:
        subprocess.run(command, check=True)
        print("✅ Nuitka build completed successfully!")
        print("The bundled application is in 'main.dist/' folder.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Nuitka build failed with error code {e.returncode}")

if __name__ == "__main__":
    # Ensure bin directory has what we need
    if not os.path.exists("bin/ffmpeg.exe") or not os.path.exists("bin/ffprobe.exe"):
        print("⚠️ WARNING: ffmpeg.exe or ffprobe.exe not found in bin/ folder. Proceeding anyway, but video processing features may fail.")
    
    run_nuitka()
