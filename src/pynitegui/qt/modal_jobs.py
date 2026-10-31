"""Modal jobs use the existing isolated/cancellable analysis supervisor."""
import contextlib
import io
from dataclasses import dataclass
from threading import Event
import uuid

from PySide6.QtCore import QObject,Signal,QThread
from .analysis_jobs import execute_analysis,AnalysisCancelled,CANCELLED
from .modal import ModalSettings,analyze_modal,modal_issue


@dataclass
class ModalRequest:
    project: object
    settings: ModalSettings


def modal_child(connection,request):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            result=analyze_modal(request.project,request.settings,lambda phase:connection.send(('progress',phase)))
        connection.send(('finished',result,''))
    except Exception as error:
        with contextlib.suppress(BrokenPipeError,EOFError,OSError):connection.send(('finished',None,str(error)))
    finally:connection.close()


class ModalWorker(QObject):
    finished=Signal(object,str)
    progress=Signal(str)

    def __init__(self,request):
        super().__init__();self.request=request;self.cancelled=Event()

    def cancel(self):self.cancelled.set()

    def run(self):
        try:self.finished.emit(execute_analysis(self.request,self.progress.emit,self.cancelled,target=modal_child),'')
        except AnalysisCancelled:self.finished.emit(None,CANCELLED)
        except Exception as error:self.finished.emit(None,str(error))


class ModalController(QObject):
    changed=Signal()

    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.result=None;self.last_settings=None;self.state='Not analyzed';self.error=''
        self.revision=None;self.session=None;self.job_id=None;self.phase='';self.panel=None
        window.undo.indexChanged.connect(lambda index:self.changed.emit())

    def start(self,settings,*,automation=False):
        w=self.window
        if w.thread is not None:raise ValueError('An analysis is already running.')
        w.project.validate();settings.validate(w.project)
        issue=modal_issue(w.project)
        if issue:raise ValueError(issue)
        w.live_analysis.discard();w.view.cancel()
        self.last_settings=settings;self.result=None;self.error='';self.state='Analyzing';self.phase='Starting modal analysis'
        self.job_id=uuid.uuid4().hex;self.session=w.project_session;self.revision=w.revision
        w.analysis_kind='modal';w.analysis_job_id=self.job_id;w.analysis_job_session=self.session;w.analysis_revision=self.revision
        w.analysis_automatic=False;w.analysis_remote=automation
        w.analysis_cancel_requested=False;w.analysis_error=''
        w.analyze_action.setEnabled(False);w.cancel_analysis_action.setEnabled(True)
        w.analysis_phase.setText(self.phase)
        for widget in (w.analysis_phase,w.analysis_progress,w.analysis_cancel_button):widget.show()
        w.statusBar().showMessage(self.phase)
        w.thread=QThread(w);w.worker=ModalWorker(ModalRequest(w.project.clone(),settings))
        w.worker.moveToThread(w.thread)
        w.thread.started.connect(w.worker.run)
        w.worker.progress.connect(self.progressed)
        w.worker.finished.connect(self.finished)
        w.worker.finished.connect(w.thread.quit)
        w.worker.finished.connect(w.worker.deleteLater)
        w.thread.finished.connect(w.analysis_stopped)
        w.thread.finished.connect(self.changed.emit)
        w.thread.start();self.changed.emit()

    def progressed(self,phase):
        if self.window.analysis_cancel_requested:return
        self.phase=phase;self.window.analysis_phase.setText(phase);self.window.statusBar().showMessage(phase);self.changed.emit()

    def cancel(self):
        w=self.window
        w.live_analysis.discard()
        if w.thread is None or w.worker is None:return
        w.analysis_cancel_requested=True;w.worker.cancel();self.state='Cancelling';self.phase='Cancelling modal analysis'
        w.cancel_analysis_action.setEnabled(False);w.analysis_phase.setText(self.phase);w.statusBar().showMessage(self.phase);self.changed.emit()

    def finished(self,result,error):
        w=self.window
        if w.analysis_cancel_requested or error==CANCELLED:
            self.state,self.error='Cancelled',''
        elif self.session!=w.project_session or self.revision!=w.revision:
            self.state,self.error='Outdated','Model changed during modal analysis; run it again.'
        elif error:
            self.state,self.error='Failed',error
        else:self.state,self.error,self.result='Current','',result
        self.phase='';w.analysis_error=self.error
        w.statusBar().showMessage('Modal analysis '+('complete' if self.state=='Current' else self.state.lower()))
        self.changed.emit()

    def status(self):
        w=self.window
        current=self.session==w.project_session and self.revision==w.revision
        state=self.state if current or self.state=='Not analyzed' else 'Outdated'
        running=w.thread is not None and getattr(w,'analysis_kind','static')=='modal'
        snapshot=self.result.metadata() if self.result is not None else None
        return dict(job_id=self.job_id,running=running,job_session_id=self.session,job_model_revision=self.revision,
                    analysis_kind='modal',phase=self.phase if running else '',state=state,error=self.error,
                    snapshot=snapshot,available_combinations=[],available_modes=list(range(1,len(self.result.frequencies)+1)) if self.result is not None else [])

    def show(self):
        from .modal_window import ModalWindow
        if self.panel is None:self.panel=ModalWindow(self.window,self)
        self.panel.show();self.panel.raise_();self.panel.activateWindow();self.changed.emit()


def controller(window):
    if not hasattr(window,'_modal_controller'):window._modal_controller=ModalController(window)
    return window._modal_controller
