"""Backward-compatible launcher for the local client demo."""
from server.services.local_demo import build_server
from server.run import main as run_service, ROOT


def main():
    import sys
    run_service(['--service-dir', str(ROOT / 'services/mahjong-ways2'), *sys.argv[1:]])

if __name__ == '__main__':
    main()
