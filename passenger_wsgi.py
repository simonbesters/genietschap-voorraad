import os
import sys

# Ensure the app directory is on the Python path and is the working directory
app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)
os.chdir(app_dir)

from app import app as application
