#!/usr/bin/env python3
"""
Generate PIN_HASH and PIN_SALT for .env.
Usage: python scripts/generate_pin_hash.py YOUR_PIN
"""
import sys
from pathlib import Path

# Ensure project root is on path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.auth import AuthService

def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_pin_hash.py YOUR_PIN", file=sys.stderr)
        sys.exit(1)
    pin = sys.argv[1]
    pin_hash, pin_salt = AuthService.hash_pin(pin)
    print("Add these to your .env file:")
    print(f"PIN_HASH={pin_hash}")
    print(f"PIN_SALT={pin_salt}")

if __name__ == "__main__":
    main()
