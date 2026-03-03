#!/bin/bash
set -e
echo "Deploying sanjai-insight..."
pytest tests/ -v --tb=short
railway up --detach
echo "Deployment complete!"
