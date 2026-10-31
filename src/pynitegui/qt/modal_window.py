"""Separate native vibration-mode workspace with frozen, labelled results."""
import csv
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView,QComboBox,QDialogButtonBox,QFileDialog,QFormLayout,QHBoxLayout,
    QLabel,QMessageBox,QPushButton,QSpinBox,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QVBoxLayout,QWidget)
from .modal import ModalSettings,STANDARD_GRAVITY,interpolation
from .modal_results import modal_table
from .theme import colors,style_axes


class ModalWindow(QWidget):
    def __init__(self,window,controller):
        super().__init__(window,Qt.WindowType.Window)
        self.window,self.controller=window,controller
        self.setProperty('pynitegui_non_model_controls',True)
        self.units=window.project.units;self.result=None
        self.setWindowTitle('Vibration Modes | Brecon');self.resize(1150,850)
        layout=QVBoxLayout(self)
        note=QLabel('Small free vibrations of an unreleased bilateral elastic frame. Select a weight combination, global force direction and gravity. Each selected weight component becomes positive mass. Density contributes only through selected generated self-weight. These are mode shapes; earthquake response, damping and static force results are separate analyses.')
        note.setWordWrap(True);layout.addWidget(note)
        inputs=QHBoxLayout();form=QFormLayout();inputs.addLayout(form)
        self.combination=QComboBox();self.combination.setObjectName('modal_mass_combination')
        self.direction=QComboBox();self.direction.addItems(['X','Y']+(['Z'] if getattr(window.project,'dimension','2D')=='3D' else []));self.direction.setCurrentText('Y')
        self.direction.setObjectName('modal_mass_direction')
        self.modes=QSpinBox();self.modes.setRange(1,50);self.modes.setValue(3);self.modes.setObjectName('modal_mode_count')
        from .app import unit_number
        self.gravity=unit_number(STANDARD_GRAVITY,self.units,'length',1e-9,decimals=10);self.gravity.setObjectName('modal_gravity')
        form.addRow('Mass-source combination',self.combination);form.addRow('Weight component (global)',self.direction)
        form.addRow('Modes to request',self.modes);form.addRow(f'Gravity ({self.units.length}/s²)',self.gravity)
        controls=QVBoxLayout();inputs.addLayout(controls)
        self.solve=QPushButton('Analyze modes');self.solve.setObjectName('modal_solve');self.solve.clicked.connect(self.start)
        self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(controller.cancel)
        self.export=QPushButton('Export current table (CSV)…');self.export.clicked.connect(self.export_csv)
        self.recipe=QPushButton('Export modal snapshot (JSON)…');self.recipe.clicked.connect(self.export_json)
        for button in (self.solve,self.cancel,self.export,self.recipe):controls.addWidget(button)
        controls.addStretch();layout.addLayout(inputs)
        self.status=QLabel('Choose a mass source and analyze.');self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        splitter=QSplitter(Qt.Orientation.Vertical);layout.addWidget(splitter,1)
        self.tabs=QTabWidget();splitter.addWidget(self.tabs);self.tables={}
        for kind,title in (('frequencies','Frequencies'),('shapes','Node mode shapes'),('mass_sources','Mass source')):
            table=QTableWidget();table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.tables[kind]=table;self.tabs.addTab(table,title)
        self.tables['frequencies'].cellClicked.connect(lambda row,col:self.mode.setCurrentIndex(row))
        plot=QWidget();plot_layout=QVBoxLayout(plot);plot_controls=QHBoxLayout();plot_layout.addLayout(plot_controls)
        self.mode=QComboBox();self.mode.setObjectName('modal_selected_mode');self.mode.currentIndexChanged.connect(self.mode_changed)
        self.amplitude=unit_number(1.,self.units,'length',0.,decimals=8);self.amplitude.setObjectName('modal_amplitude')
        self.amplitude.valueChanged.connect(self.draw)
        self.amplitude_label=QLabel('Display amplitude')
        plot_controls.addWidget(QLabel('Mode'));plot_controls.addWidget(self.mode,1);plot_controls.addWidget(self.amplitude_label);plot_controls.addWidget(self.amplitude)
        self.figure=Figure();self.canvas=FigureCanvasQTAgg(self.figure);plot_layout.addWidget(self.canvas,1)
        from .plot_export import SnapshotPlotToolbar
        self.toolbar=SnapshotPlotToolbar(self.canvas,self,self.plot_metadata)
        plot_layout.insertWidget(1,self.toolbar)
        splitter.addWidget(plot);splitter.setSizes([240,430])
        self.refresh_choices();controller.changed.connect(self.refresh)
        if controller.last_settings is not None:self.set_inputs(controller.last_settings)
        self.refresh()

    def refresh_choices(self):
        names=list(self.window.project.combinations)
        if [self.combination.itemText(i) for i in range(self.combination.count())]!=names:
            selected=self.combination.currentText();self.combination.clear();self.combination.addItems(names)
            if selected in names:self.combination.setCurrentText(selected)
        directions=['X','Y']+(['Z'] if getattr(self.window.project,'dimension','2D')=='3D' else [])
        if [self.direction.itemText(i) for i in range(self.direction.count())]!=directions:
            selected=self.direction.currentText();self.direction.clear();self.direction.addItems(directions)
            self.direction.setCurrentText(selected if selected in directions else 'Y')

    def set_inputs(self,settings):
        self.refresh_choices();self.combination.setCurrentText(settings.combination);self.modes.setValue(settings.modes)
        self.direction.setCurrentText(settings.direction);self.gravity.setValue(self.units.to_display(settings.gravity,'length'))

    def start(self):
        from .app import unit_value
        self.gravity.interpretText()
        settings=ModalSettings(self.combination.currentText(),self.modes.value(),self.direction.currentText(),unit_value(self.gravity,self.units,'length'))
        try:self.controller.start(settings)
        except ValueError as error:QMessageBox.information(self,'Modal Analysis',str(error))

    def refresh(self):
        self.refresh_choices();status=self.controller.status();running=self.window.thread is not None
        self.solve.setEnabled(not running and not self.window.mcp_mode)
        self.cancel.setEnabled(status['running'] and status['state']!='Cancelling' and not self.window.mcp_mode)
        fresh=self.controller.result
        if fresh is not None and (self.result is None or fresh.snapshot_id!=self.result.snapshot_id):
            self.result=fresh;self.mode.blockSignals(True);self.mode.clear()
            for i,f in enumerate(fresh.frequencies):self.mode.addItem(f'{i+1}: {f:.6g} Hz',i)
            self.mode.blockSignals(False)
            self.fill('frequencies');self.fill('mass_sources');self.mode_changed()
        label=status['phase'] or status['state']
        if status['error']:label+=' | '+status['error']
        if self.result is not None:
            r=self.result
            label+=f' | Snapshot {r.snapshot_id} | {r.analyzed_at} | Mass: {r.settings.combination} | {r.settings.direction} | gravity {self.units.to_display(r.settings.gravity,"length"):.9g} {self.units.length}/s²'
            if fresh is None:label+=' | Showing previous snapshot'
        self.status.setText(label)
        self.export.setEnabled(self.result is not None and not self.window.mcp_mode);self.recipe.setEnabled(self.export.isEnabled())
        self.toolbar.setEnabled(self.export.isEnabled())

    def fill(self,kind):
        if self.result is None:return
        headers,rows=modal_table(self.result,self.units,kind,max(1,self.mode.currentIndex()+1))
        table=self.tables[kind];table.setColumnCount(len(headers));table.setHorizontalHeaderLabels(headers);table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):table.setItem(i,j,QTableWidgetItem(value if isinstance(value,str) else f'{value:.9g}'))
        table.resizeColumnsToContents()

    def mode_changed(self):
        if self.result is None or self.mode.currentIndex()<0:return
        i=self.mode.currentIndex();rotation=self.result.normalization[i]=='rotation'
        coords=np.array([node.coords if hasattr(node,'coords') else (node.x,node.y,0.) for node in self.result.project.nodes.values()])
        span=max(float(np.linalg.norm(np.ptp(coords,axis=0))),1.)
        self.amplitude.blockSignals(True)
        self.amplitude.setProperty('quantity','rotation' if rotation else 'length')
        self.amplitude.setValue(.05 if rotation else self.units.to_display(.08*span,'length'))
        self.amplitude.blockSignals(False)
        self.amplitude_label.setText('Display rotation (rad)' if rotation else f'Display amplitude ({self.units.length})')
        self.fill('shapes');self.draw()

    def draw(self):
        if self.result is None or self.mode.currentIndex()<0:return
        r=self.result;p=r.project;mode=self.mode.currentIndex();shape=r.shapes[mode]
        rotation=r.normalization[mode]=='rotation'
        amplitude=self.amplitude.value() if rotation else self.units.from_display(self.amplitude.value(),'length')
        self.figure.clear();spatial=getattr(p,'dimension','2D')=='3D'
        axes=self.figure.add_subplot(111,projection='3d') if spatial else self.figure.add_subplot(111)
        palette=colors();style_axes(axes)
        order={name:i for i,name in enumerate(p.nodes)}
        for name,member in p.members.items():
            a,b=(np.r_[p.nodes[key].coords] if spatial else np.array((p.nodes[key].x,p.nodes[key].y,0.)) for key in (member.start,member.end))
            length=float(np.linalg.norm(b-a));R=r.axes[name]
            end=np.r_[R @ shape[order[member.start],:3],R @ shape[order[member.start],3:],R @ shape[order[member.end],:3],R @ shape[order[member.end],3:]]
            t=np.linspace(0.,1.,25)
            original=np.array([a+(b-a)*x for x in t]);deformed=original+amplitude*np.array([R.T @ (interpolation(length,x) @ end) for x in t])
            original*=self.units.length_factor;deformed*=self.units.length_factor
            if spatial:
                axes.plot(original[:,0],original[:,2],original[:,1],color=palette['muted'],linestyle='--',linewidth=1.)
                axes.plot(deformed[:,0],deformed[:,2],deformed[:,1],color=palette['accent'],linewidth=2.)
                # Section orientation ticks make axial-twist modes visible even
                # when their centreline translations vanish.
                radius=.025*max(length,1.)
                for x in (.25,.5,.75):
                    twist=amplitude*((1-x)*end[3]+x*end[9]);center=a+(b-a)*x
                    arm=R.T @ np.array((0.,radius*np.cos(twist),radius*np.sin(twist)))
                    tick=np.array([center-arm,center+arm])*self.units.length_factor
                    axes.plot(tick[:,0],tick[:,2],tick[:,1],color=palette['accent'],linewidth=1.)
            else:
                axes.plot(original[:,0],original[:,1],color=palette['muted'],linestyle='--',linewidth=1.)
                axes.plot(deformed[:,0],deformed[:,1],color=palette['accent'],linewidth=2.)
        axes.set_xlabel(f'X ({self.units.length})')
        axes.set_ylabel(f'{"Z" if spatial else "Y"} ({self.units.length})')
        if spatial:axes.set_zlabel(f'Y ({self.units.length})')
        else:axes.set_aspect('equal',adjustable='datalim')
        axes.set_title(f'Mode {mode+1} | {r.frequencies[mode]:.6g} Hz | {r.periods[mode]:.6g} s | Snapshot {r.snapshot_id}')
        self.figure.tight_layout();self.canvas.draw_idle()

    def plot_metadata(self):
        if self.result is None:raise ValueError('Analyze modes before exporting a plot.')
        from pynitegui import __version__
        mode=self.mode.currentIndex()+1
        return {**self.result.metadata(),'application':f'Brecon {__version__}',
                'plot':f'Vibration mode {mode}','analysis_method':'Modal (elastic)',
                'combinations':[f'Mode {mode}'],'units':self.units.summary,
                'frequency_hz':float(self.result.frequencies[mode-1]),'display_amplitude':self.amplitude.value(),
                'amplitude_unit':'rad' if self.result.normalization[mode-1]=='rotation' else self.units.length}

    def export_csv(self):
        if self.result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export Modal Table','','CSV files (*.csv)')
        if not path:return
        kind=list(self.tables)[self.tabs.currentIndex()]
        headers,rows=modal_table(self.result,self.units,kind,self.mode.currentIndex()+1)
        from .reports import csv_text
        def write(stream):
            r=self.result
            writer=csv.writer(stream);writer.writerow(['Analysis','Modal','Snapshot',r.snapshot_id,
                'Analyzed (UTC)',r.analyzed_at,'Model signature',r.model_signature,'Configuration',r.configuration_signature,
                'Mass combination',r.settings.combination,'Weight direction',r.settings.direction,
                'Gravity (in/s²)',r.settings.gravity,'Engine',r.engine_version,'Units',self.units.key,
                'Table',kind,'Mode',self.mode.currentIndex()+1 if kind=='shapes' else 'All'])
            writer.writerow(headers);writer.writerows([[csv_text(v) for v in row] for row in rows])
        self.write_file(path,write)

    def export_json(self):
        if self.result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save Modal Snapshot','','JSON files (*.json)')
        if not path:return
        r=self.result
        data={**r.metadata(),'project':r.project.to_dict(),'frequencies_hz':r.frequencies.tolist(),'canonical_shapes':r.shapes.tolist(),
              'axes':{name:axis.tolist() for name,axis in r.axes.items()},'mass_sources':r.source,'eigen_residuals':r.residuals.tolist()}
        self.write_file(path,lambda stream:json.dump(data,stream,indent=2,allow_nan=False))

    def write_file(self,path,write):
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=Path(path).parent,delete=False) as stream:
                temporary=Path(stream.name);write(stream);stream.flush();os.fsync(stream.fileno())
            temporary.replace(path)
        except (OSError,ValueError) as error:QMessageBox.warning(self,'Modal Export',str(error))
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
