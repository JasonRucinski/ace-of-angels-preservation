"""Old command lines that still name a disassembly cache; standard library only."""
import sys


def drop_cache_args(argv, positions=(1,)):
    """argv without the old disassembly-cache arguments (a .pkl at these positional indexes).

    The disassembly cache is now kept by the executable's SHA-256 in
    work/cache/ (aoa.analysis.pe_util.Disasm), so an old command line that
    still names one parses, with a note on stderr.
    """
    argv = sys.argv[1:] if argv is None else list(argv)
    kept, index = [], 0
    for arg in argv:
        if arg.startswith("-") and arg != "-":
            kept.append(arg)
            continue
        if index in positions and arg.lower().endswith(".pkl"):
            print(f"note: ignoring {arg}: the disassembly cache is work/cache/<sha256 of the executable>.pkl",
                  file=sys.stderr)
        else:
            kept.append(arg)
        index += 1
    return kept
