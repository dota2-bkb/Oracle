import PyInstaller.__main__
import os
import shutil

# Clean dist/build folders
if os.path.exists("dist"): shutil.rmtree("dist")
if os.path.exists("build"): shutil.rmtree("build")

print("Starting Build Process...")

PyInstaller.__main__.run([
    'run_app.py',
    '--name=SentryAnalysis',
    '--onefile',
    '--clean',
    # Collect ALL dependencies explicitly to prevent missing modules
    '--collect-all=streamlit',
    '--collect-all=altair',
    '--collect-all=pandas',
    '--collect-all=sqlalchemy',
    '--collect-all=dotenv',
    '--collect-all=PIL', 
    '--collect-all=reportlab',
    '--collect-all=openpyxl', # Added openpyxl
    '--collect-all=requests', # Added requests
    '--collect-all=pydeck', # Streamlit uses this
    '--collect-all=tornado', # Streamlit server uses this
    '--collect-all=watchdog', # Streamlit file watcher
    
    # Add application files
    '--add-data=main.py;.',
    '--add-data=views;views',
    '--add-data=services;services',
    '--add-data=models.py;.',
    '--add-data=database.py;.',
    '--add-data=config.py;.',
    '--add-data=data;data', 
    '--add-data=assets;assets',
    '--add-data=secrets.toml.example;.',
    '--add-data=README_USER_MANUAL.md;.',
    # Hidden imports
    '--hidden-import=engineio.async_drivers.threading',
    # Windows specific
    '--console', # Ensure console is visible for debugging
])

print("Build Complete. Check dist/SentryAnalysis.exe")

