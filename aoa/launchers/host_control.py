"""The host window's old module name: main() opens aoa/launchers/host_app.py.

Its settings (work/host/host_control.json) are migrated once into
work/settings.json by aoa/launchers/settings.py; the command line comes from
HostConfig and the process handling from the headless host's Supervisor.
"""


def main(argv=None):
    from aoa.launchers import host_app
    return host_app.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
