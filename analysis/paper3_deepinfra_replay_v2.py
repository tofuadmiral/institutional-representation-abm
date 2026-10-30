"""Fresh bundled anticipation replay; no paid execution or preparation mode."""
import argparse
import importlib.util
from pathlib import Path
import sys


def main():
    if sys.flags.isolated != 1 or sys.flags.no_site != 1:
        raise ValueError("use fresh Python -I -S")
    sys.dont_write_bytecode = True
    code = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code))
    spec = importlib.util.spec_from_file_location("_recovery_offline_guard",
        code / "analysis/paper3_contracts_archive.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    sys.addaudithook(helper.offline_guard)
    # Deliberately denied before either operation can occur.
    import socket
    import subprocess
    for operation in (lambda: socket.getaddrinfo("127.0.0.1", 1),
                      lambda: subprocess.run([sys.executable, "-c", "pass"])):
        try:
            operation()
        except RuntimeError as exc:
            if str(exc) != "offline replay forbids network and child processes":
                raise
        else:
            raise ValueError("offline guard self-test failed")
    from paper3 import retrospective_deepinfra_archive_v2 as archive
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-protocol", required=True)
    args = parser.parse_args()
    print(archive.journal.canonical(archive.replay(args.root, args.expected_protocol)))


if __name__ == "__main__":
    main()
