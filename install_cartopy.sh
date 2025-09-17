#!/bin/bash

# Stop the Azure Functions host first
echo "Installing Cartopy and dependencies..."

# Install cartopy and its dependencies
pip install cartopy

# Also install shapely and proj if needed
pip install shapely proj4

# Restart functions with clean environment
echo "Installation complete. Restart your functions host with: func start --no-build"
