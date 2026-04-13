#!/usr/bin/env python3
"""
Script to migrate from --json flag to --format json option.
Updates all commands that use output_json = ctx.obj["output_json"]
"""

import re

FILE_PATH = "src/qadmcli/cli.py"

def migrate_format():
    with open(FILE_PATH, 'r') as f:
        content = f.read()
    
    # Pattern 1: Remove output_json = ctx.obj["output_json"]
    content = re.sub(
        r'\n\s*output_json = ctx\.obj\["output_json"\]\n',
        '\n',
        content
    )
    
    # Pattern 2: Replace if output_json: with if output_format == "json":
    # But only in functions that have output_format parameter
    content = re.sub(
        r'\bif output_json:',
        'if output_format == "json":',
        content
    )
    
    # Pattern 3: Replace elif output_json: 
    content = re.sub(
        r'\belif output_json:',
        'elif output_format == "json":',
        content
    )
    
    with open(FILE_PATH, 'w') as f:
        f.write(content)
    
    print("Migration completed!")
    print("Note: You still need to add @click.option('--format', ...) to each command manually")

if __name__ == "__main__":
    migrate_format()
