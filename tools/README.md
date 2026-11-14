# tools/

The commands people run. Each `tools/<name>.py` here is a short shim that
runs a module of the `aoa` package, so documented commands keep working:

```
python -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
```

Other modules run through `tools/run.py`; `python -I tools/run.py --list`
shows every one with its summary. `tools/test.py` runs the test suites
(`--tier ci`, `--tier local`) and `tools/verify_local.py` is the local gate
with the game. The PowerShell and `.cmd` files are the Windows setup and
launch scripts (`tools/dev/` holds test drivers).

The full tool reference is [docs/reference/tools.md](../docs/reference/tools.md).
