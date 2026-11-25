"""Interactively preview one IPv4 using the shared geolocation CLI."""
import sys

from enrich_sourceip import main


if __name__ == '__main__':
    sys.argv = [sys.argv[0], '--ip', input('IPv4: ').strip()]
    main()
