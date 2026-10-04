"""Isolated analysis processes supervised off the GUI thread."""
import contextlib
import io
import multiprocessing
from threading import Event

from PySide6.QtCore import QObject, Signal

from .analysis import analyze


CANCELLED = "Analysis cancelled"


class AnalysisCancelled(Exception):
    pass


def analysis_child(connection, project):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result = analyze(project, progress=lambda phase: connection.send(("progress", phase)))
        connection.send(("finished", result, ""))
    except Exception as error:
        with contextlib.suppress(BrokenPipeError, EOFError, OSError):
            connection.send(("finished", None, str(error)))
    finally:
        connection.close()


def execute_analysis(project, progress, cancelled, *, target=None):
    if cancelled.is_set():
        raise AnalysisCancelled()
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=target or analysis_child, args=(sender, project), daemon=True)
    started = False
    try:
        process.start()
        started = True
        sender.close()
        while True:
            if cancelled.is_set():
                raise AnalysisCancelled()
            if receiver.poll(0.05):
                try:
                    message = receiver.recv()
                except EOFError as error:
                    raise RuntimeError("The analysis process exited without a complete result.") from error
                if cancelled.is_set():
                    raise AnalysisCancelled()
                if message[0] == "progress":
                    progress(message[1])
                elif message[0] == "finished":
                    if message[2]:
                        raise ValueError(message[2])
                    return message[1]
            elif not process.is_alive():
                if receiver.poll():
                    continue
                raise RuntimeError(f"The analysis process stopped unexpectedly (exit code {process.exitcode}).")
    finally:
        receiver.close()
        sender.close()
        if started:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join()
        process.close()


class AnalysisWorker(QObject):
    finished = Signal(object, str)
    progress = Signal(str)

    def __init__(self, project):
        super().__init__()
        self.project = project
        self.cancelled = Event()

    def cancel(self):
        # Called directly by the GUI thread; a queued slot cannot run while the
        # worker's blocking supervisor loop is active. Event is thread-safe.
        self.cancelled.set()

    def run(self):
        try:
            self.finished.emit(execute_analysis(self.project, self.progress.emit, self.cancelled), "")
        except AnalysisCancelled:
            self.finished.emit(None, CANCELLED)
        except Exception as error:
            self.finished.emit(None, str(error))
