"""
cPanel Passenger WSGI entry point.
Place this file in the application root and set it as the startup file
in cPanel Python App Manager.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from backend.main import app as application
