"""Frozen application entry; dispatch spawned workers before importing Qt."""
if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    import os
    import sys
    # Windowed bootloaders need writable streams for dependency logging.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) == 3 and sys.argv[1] == "--desktop-check":
        from desktop_check import run
        run(sys.argv[2])
    else:
        from brecon import main
        main()
