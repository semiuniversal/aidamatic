import subprocess
from aidamatic.cli.aida_stop import main as stop_main
from aidamatic.cli.aidastart import main as start_main


def main() -> int:
	stop_main()
	return start_main()


if __name__ == "__main__":
	raise SystemExit(main())
