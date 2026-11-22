"""
Simple script to run the Pneumonia Detection Flask Application
"""

import os
import sys

print("\n" + "="*60)
print("PNEUMONIA DETECTION WEB APPLICATION")
print("="*60)
print("\nStarting Flask server...")
print("Application will be available at: http://127.0.0.1:5002")
print("\nPress Ctrl+C to stop the server")
print("="*60 + "\n")

# Run the Flask app
# Use sys.executable to ensure we use the same python interpreter
os.system(f'"{sys.executable}" app.py')
