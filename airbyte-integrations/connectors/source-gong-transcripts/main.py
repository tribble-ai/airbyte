#!/usr/bin/env python3

import sys
import yaml
from pathlib import Path
from airbyte_cdk.entrypoint import launch
from airbyte_cdk.sources.declarative.manifest_declarative_source import ManifestDeclarativeSource

if __name__ == "__main__":
    # Load the manifest yaml file
    manifest_path = Path(__file__).parent / "manifest.yaml"
    
    with open(manifest_path, 'r') as f:
        source_config = yaml.safe_load(f)
    
    # Create source with the loaded config
    source = ManifestDeclarativeSource(source_config=source_config)
    
    launch(source, sys.argv[1:])