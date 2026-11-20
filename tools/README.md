# tools/

The commands people run. Each `tools/<name>.py` that is a shim runs a module
of the `aoa` package, so documented commands keep working:

```
python -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
```

Every other module with a command line runs through `tools/run.py`
(`python -I tools/run.py --list` shows them). `tools/test.py` runs the test
suites and `tools/verify_local.py` is the local gate with the game.

The index of every command and module, generated from their docstrings, is
[docs/reference/tools.md](../docs/reference/tools.md).
