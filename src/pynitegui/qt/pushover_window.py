"""Independent native workspace for checked steel pushover histories."""
import csv
import json
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView,QCheckBox,QComboBox,QDoubleSpinBox,QFileDialog,QFormLayout,
    QHBoxLayout,QLabel,QListWidget,QListWidgetItem,QMessageBox,QPushButton,QSpinBox,QSplitter,
    QTableWidget,QTableWidgetItem,QTabWidget,QVBoxLayout,QWidget)
from .pushover import PushoverSettings
from .pushover_results import pushover_table
from .modal_window import ModalWindow
from .theme import colors,style_axes


class PushoverWindow(QWidget):
    write_file=ModalWindow.write_file

    def __init__(self,window,controller):
        super().__init__(window,Qt.WindowType.Window)
        self.window,self.controller=window,controller;self.units=window.project.units;self.result=None
        self.setProperty('pynitegui_non_model_controls',True)
        self.setWindowTitle('Steel Pushover | Brecon');self.resize(1200,930)
        layout=QVBoxLayout(self)
        note=QLabel('First-order steel I-section axial/biaxial-bending plasticity at explicit member ends. Define material fy and section Zy/Zz with a matching steel material. Keep preload elastic; push with joint forces/moments or member-end point loads. No P-Delta, reinforced concrete, hardening, shear/torsional yielding or post-mechanism response. Refine load steps and member divisions before interpreting a capacity limit.')
        note.setWordWrap(True);layout.addWidget(note)
        inputs=QHBoxLayout();layout.addLayout(inputs);form=QFormLayout();inputs.addLayout(form,2)
        self.preload=QComboBox();self.push=QComboBox();self.node=QComboBox();self.direction=QComboBox()
        self.limit=QDoubleSpinBox();self.limit.setRange(1e-9,1e12);self.limit.setDecimals(9);self.limit.setValue(self.units.to_display(2.,'length'))
        self.limit_label=QLabel();self.direction.currentTextChanged.connect(self.limit_unit)
        self.steps=QSpinBox();self.steps.setRange(1,2000);self.steps.setValue(500)
        self.retries=QSpinBox();self.retries.setRange(1,500);self.retries.setValue(30)
        self.tolerance=QDoubleSpinBox();self.tolerance.setRange(0.,.02);self.tolerance.setDecimals(5);self.tolerance.setValue(.01)
        for label,widget in (('Elastic preload',self.preload),('Full push pattern',self.push),('Control node',self.node),('Control DOF',self.direction),
                             (self.limit_label,self.limit),('Load steps',self.steps),('Step retries',self.retries),('Yield overshoot tolerance (Φ)',self.tolerance)):
            form.addRow(label,widget)
        base=QVBoxLayout();inputs.addLayout(base,1);base.addWidget(QLabel('Select reaction nodes'))
        self.bases=QListWidget();self.bases.setMaximumHeight(140);base.addWidget(self.bases)
        self.component=QComboBox();base.addWidget(QLabel('Sum reaction component'));base.addWidget(self.component);base.addStretch()
        controls=QVBoxLayout();inputs.addLayout(controls,1)
        self.solve=QPushButton('Run steel pushover');self.solve.clicked.connect(self.start)
        self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(controller.cancel)
        self.materials=QPushButton('Materials…');self.materials.clicked.connect(window.manage_materials)
        self.sections=QPushButton('Sections…');self.sections.clicked.connect(window.manage_sections)
        self.export=QPushButton('Export current table (CSV)…');self.export.clicked.connect(self.export_csv)
        self.recipe=QPushButton('Export snapshot (JSON)…');self.recipe.clicked.connect(self.export_json)
        for button in (self.solve,self.cancel,self.materials,self.sections,self.export,self.recipe):controls.addWidget(button)
        controls.addStretch()
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);layout.addWidget(self.status)
        selected=QHBoxLayout();layout.addLayout(selected);selected.addWidget(QLabel('Accepted step (0 = preload)'))
        self.step=QComboBox();self.step.currentIndexChanged.connect(self.step_changed);selected.addWidget(self.step,1)
        self.magnitudes=QCheckBox('Plot magnitudes');self.magnitudes.toggled.connect(self.draw);selected.addWidget(self.magnitudes)
        split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split,1)
        self.tabs=QTabWidget();split.addWidget(self.tabs);self.tables={}
        for kind,title in (('capacity','Capacity'),('displacements','Joint motions'),('reactions','Reactions'),('member_ends','Member-end actions'),('equilibrium','Equilibrium')):
            table=QTableWidget();table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.tables[kind]=table;self.tabs.addTab(table,title)
        self.tables['capacity'].cellClicked.connect(lambda row,col:self.step.setCurrentIndex(row))
        plot=QWidget();plot_layout=QVBoxLayout(plot);self.figure=Figure();self.canvas=FigureCanvasQTAgg(self.figure)
        from .plot_export import SnapshotPlotToolbar
        self.toolbar=SnapshotPlotToolbar(self.canvas,self,self.plot_metadata);plot_layout.addWidget(self.toolbar);plot_layout.addWidget(self.canvas,1)
        split.addWidget(plot);split.setSizes([220,340])
        for name in ('preload','push','node','direction','limit','steps','retries','tolerance','bases','component','step','solve'):
            getattr(self,name).setObjectName('pushover_'+name)
        self.refresh_choices();controller.changed.connect(self.refresh)
        if controller.last_settings is not None:self.set_inputs(controller.last_settings)
        self.refresh()

    def refresh_choices(self):
        p=self.window.project;spatial=getattr(p,'dimension','2D')=='3D'
        for combo,names in ((self.preload,list(p.combinations)),(self.push,list(p.combinations)),(self.node,list(p.nodes)),
                            (self.direction,['DX','DY','DZ','RX','RY','RZ'] if spatial else ['DX','DY','RZ']),
                            (self.component,['FX','FY','FZ','MX','MY','MZ'] if spatial else ['FX','FY','MZ'])):
            if [combo.itemText(i) for i in range(combo.count())]!=names:
                old=combo.currentText();combo.clear();combo.addItems(names)
                if old in names:combo.setCurrentText(old)
        names=[name for name,n in p.nodes.items() if any(n.restraints) or any(n.springs)]
        if [self.bases.item(i).text() for i in range(self.bases.count())]!=names:
            selected=self.base_nodes();self.bases.clear()
            for name in names:
                item=QListWidgetItem(name);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in selected else Qt.CheckState.Unchecked);self.bases.addItem(item)
        self.limit_unit()

    def base_nodes(self):
        return tuple(self.bases.item(i).text() for i in range(self.bases.count()) if self.bases.item(i).checkState()==Qt.CheckState.Checked)

    def limit_unit(self):
        self.limit_label.setText('Absolute stop limit ('+('rad' if self.direction.currentText().startswith('R') else self.units.length)+')')

    def set_inputs(self,s):
        self.refresh_choices()
        for widget,value in ((self.preload,s.preload),(self.push,s.push),(self.node,s.control_node),(self.direction,s.control_direction),(self.component,s.resultant)):
            widget.setCurrentText(value)
        self.limit.setValue(self.units.to_display(s.stop_limit,'rotation' if s.control_direction.startswith('R') else 'length'))
        self.steps.setValue(s.steps);self.retries.setValue(s.iteration_limit);self.tolerance.setValue(s.yield_tolerance)
        for i in range(self.bases.count()):
            self.bases.item(i).setCheckState(Qt.CheckState.Checked if self.bases.item(i).text() in s.base_nodes else Qt.CheckState.Unchecked)

    def start(self):
        self.limit.interpretText()
        s=PushoverSettings(self.preload.currentText(),self.push.currentText(),self.node.currentText(),self.direction.currentText(),
            self.units.from_display(self.limit.value(),'rotation' if self.direction.currentText().startswith('R') else 'length'),
            self.base_nodes(),self.component.currentText(),self.steps.value(),self.retries.value(),self.tolerance.value())
        try:self.controller.start(s)
        except ValueError as error:QMessageBox.information(self,'Steel Pushover',str(error))

    def refresh(self):
        self.refresh_choices();status=self.controller.status();idle=self.window.thread is None and not self.window.mcp_mode
        for widget in (self.solve,self.materials,self.sections):widget.setEnabled(idle)
        self.cancel.setEnabled(status['running'] and status['state']!='Cancelling' and not self.window.mcp_mode)
        fresh=self.controller.result
        if fresh is not None and (self.result is None or fresh.snapshot_id!=self.result.snapshot_id):
            self.result=fresh;self.step.blockSignals(True);self.step.clear()
            for i,factor in enumerate(fresh.factors):self.step.addItem(f'{i}: push factor {factor:.6g}',i)
            self.step.setCurrentIndex(len(fresh.factors)-1);self.step.blockSignals(False);self.step_changed()
        label=status['phase'] or status['state']
        if status['error']:label+=' | '+status['error']
        if self.result is not None:
            r=self.result;label+=f' | Snapshot {r.snapshot_id} | Accepted {len(r.factors)-1}/{r.settings.steps} | {r.termination} | {r.analyzed_at}'
            if fresh is None:label+=' | Showing previous snapshot'
        self.status.setText(label)
        enabled=self.result is not None and not self.window.mcp_mode
        for widget in (self.export,self.recipe,self.toolbar):widget.setEnabled(enabled)

    def step_changed(self):
        if self.result is None or self.step.currentIndex()<0:return
        for kind,table in self.tables.items():
            headers,rows=pushover_table(self.result,self.units,kind,self.step.currentIndex())
            table.setColumnCount(len(headers));table.setHorizontalHeaderLabels(headers);table.setRowCount(len(rows))
            for i,row in enumerate(rows):
                for j,value in enumerate(row):table.setItem(i,j,QTableWidgetItem('' if value is None else value if isinstance(value,str) else f'{value:.9g}'))
            table.resizeColumnsToContents()
        capacity=self.tables['capacity'];capacity.selectRow(self.step.currentIndex());capacity.scrollToItem(capacity.item(self.step.currentIndex(),0))
        self.draw()

    def draw(self):
        if self.result is None or self.step.currentIndex()<0:return
        r=self.result;s=r.settings;index=self.step.currentIndex();self.figure.clear();palette=colors()
        curve=self.figure.add_subplot(121);style_axes(curve)
        x=np.array([self.units.to_display(v,'rotation' if s.control_direction.startswith('R') else 'length') for v in r.curve[:,0]])
        y=np.array([self.units.to_display(v,'force' if s.resultant.startswith('F') else 'moment') for v in r.curve[:,1]])
        if self.magnitudes.isChecked():x,y=abs(x),abs(y)
        curve.plot(x,y,color=palette['accent']);curve.plot(x[index],y[index],'o',color=palette['accent'])
        curve.set_xlabel(f'{s.control_node} {s.control_direction} ({"rad" if s.control_direction.startswith("R") else self.units.length})')
        curve.set_ylabel(f'Selected supports Σ{s.resultant} ({self.units.force if s.resultant.startswith("F") else self.units.moment})')
        curve.set_title(('Complete target' if r.complete else 'Partial checked history')+(' | magnitudes' if self.magnitudes.isChecked() else ' | signed'))
        p=r.project;spatial=getattr(p,'dimension','2D')=='3D'
        axes=self.figure.add_subplot(122,projection='3d') if spatial else self.figure.add_subplot(122);style_axes(axes)
        for i,(name,m) in enumerate(p.members.items()):
            points=np.array([p.nodes[n].coords if spatial else (p.nodes[n].x,p.nodes[n].y,0.) for n in (m.start,m.end)])*self.units.length_factor
            projected=points[:,[0,2,1]] if spatial else points[:,:2]
            axes.plot(*projected.T,color=palette['muted'])
            for end in (0,1):
                if r.phis[index,i,end]>=1.:
                    point=.95*projected[end]+.05*projected[1-end]
                    axes.plot(*[[v] for v in point],marker='o',color=palette['accent'])
        axes.set_xlabel(f'X ({self.units.length})');axes.set_ylabel(f'{"Z" if spatial else "Y"} ({self.units.length})')
        if spatial:axes.set_zlabel(f'Y ({self.units.length})')
        else:axes.set_aspect('equal',adjustable='datalim')
        axes.set_title(f'Undeformed end-yield map | step {index}')
        self.figure.tight_layout();self.canvas.draw_idle()

    def plot_metadata(self):
        if self.result is None:raise ValueError('Run steel pushover before exporting a plot.')
        r=self.result
        return {**r.metadata(),'plot':'Steel capacity and end-yield map','analysis_method':'First-order steel pushover'+(' (partial)' if not r.complete else ''),
                'combinations':[r.settings.preload,r.settings.push],'units':self.units.summary,'step':self.step.currentIndex(),
                'plot_magnitudes':self.magnitudes.isChecked()}

    def export_csv(self):
        if self.result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export Steel Pushover Table','','CSV files (*.csv)')
        if not path:return
        kind=list(self.tables)[self.tabs.currentIndex()];headers,rows=pushover_table(self.result,self.units,kind,self.step.currentIndex())
        from .reports import csv_text
        def write(stream):
            writer=csv.writer(stream);writer.writerow(['Steel pushover metadata',json.dumps(self.plot_metadata(),allow_nan=False)])
            writer.writerow(['Table',kind,'Step',self.step.currentIndex()]);writer.writerow(headers)
            writer.writerows([[csv_text(v) for v in row] for row in rows])
        self.write_file(path,write)

    def export_json(self):
        if self.result is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save Steel Pushover Snapshot','','JSON files (*.json)')
        if not path:return
        r=self.result;data={**r.metadata(),'project':r.project.to_dict(),'canonical_units':'in, kip, rad','end_states':r.end_states}
        for key in ('factors','displacements','reactions','end_forces','phis','curve','equilibrium','equilibrium_limits'):data[key]=getattr(r,key).tolist()
        data['axes']={name:axis.tolist() for name,axis in r.axes.items()}
        self.write_file(path,lambda stream:json.dump(data,stream,indent=2,allow_nan=False))
