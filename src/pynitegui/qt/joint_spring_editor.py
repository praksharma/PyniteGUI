"""Staged native joint-spring definitions; independent of material/section data."""
from PySide6.QtWidgets import (QAbstractItemView,QComboBox,QDialog,QDialogButtonBox,QFormLayout,QHBoxLayout,
    QLabel,QLineEdit,QMessageBox,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout)
from .joint_springs import JointSpring,BEHAVIORS,definition_table


class JointSpringEditor(QDialog):
    def __init__(self,parent,project,spring,previous=None):
        super().__init__(parent);self.project=project;self.previous=previous;self.definition=None
        self.setWindowTitle('Edit Joint Spring' if previous else 'Add Joint Spring')
        form=QFormLayout(self);self.name=QLineEdit(spring.name);self.name.setMaxLength(80)
        self.start=QComboBox();self.end=QComboBox()
        for box,selected in ((self.start,spring.start),(self.end,spring.end)):
            box.addItems(list(project.nodes));box.setCurrentText(selected)
        from .app import unit_number
        self.stiffness=unit_number(spring.stiffness,project.units,'stiffness',0.,decimals=10)
        self.behavior=QComboBox()
        for key,label in BEHAVIORS.items():self.behavior.addItem(label,key)
        self.behavior.setCurrentIndex(self.behavior.findData(spring.behavior))
        for label,widget in (('Name',self.name),('Start joint',self.start),('End joint',self.end),
                             (f'Axial stiffness ({project.units.stiffness})',self.stiffness),('Action',self.behavior)):
            form.addRow(label,widget)
        note=QLabel('Massless small-displacement axial link with zero initial force. k is entered directly; it is not EA/L. Tension/compression refer to relative chord extension, independently of endpoint order. One-way action requires Iterative elastic. No initial gap/slack, damping, torsional/rotational link or P-Delta/modal/plastic/surface coupling.')
        note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons)

    def accept(self):
        from .app import unit_value
        spring=JointSpring(self.name.text().strip(),self.start.currentText(),self.end.currentText(),
                           unit_value(self.stiffness,self.project.units,'stiffness'),self.behavior.currentData())
        candidate=self.project.clone()
        try:
            if self.previous is not None:del candidate.joint_springs[self.previous]
            if spring.name in candidate.joint_springs:raise ValueError('A joint spring already has this name.')
            candidate.joint_springs[spring.name]=spring;candidate.validate()
        except ValueError as error:QMessageBox.warning(self,'Joint Spring',str(error));return
        self.definition=spring;super().accept()


class JointSpringsDialog(QDialog):
    def __init__(self,parent,project):
        super().__init__(parent);self.project=project.clone();self.setWindowTitle('Joint Springs');self.resize(850,500)
        layout=QVBoxLayout(self)
        note=QLabel('Connect existing joints with axial springs. Node movement, deletion and 2D-to-3D conversion preserve their endpoint ownership. Copy/repeat includes links whose two endpoints are copied. Edit here; the canvas zigzag is a decorative symbol. OK applies all changes as one undo step. Springs carry no self-weight or member loads.')
        note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget();self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.table);buttons=QHBoxLayout();layout.addLayout(buttons)
        for action,label in (('add','Add…'),('edit','Edit…'),('delete','Delete')):
            button=QPushButton(label);button.clicked.connect(lambda checked=False,action=action:self.perform(action));buttons.addWidget(button)
        buttons.addStretch();self.close_buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.close_buttons.accepted.connect(self.accept);self.close_buttons.rejected.connect(self.reject);layout.addWidget(self.close_buttons)
        self.refresh()

    def refresh(self):
        headers,rows=definition_table(self.project);self.table.setColumnCount(len(headers));self.table.setHorizontalHeaderLabels(headers);self.table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):self.table.setItem(i,j,QTableWidgetItem(value if isinstance(value,str) else f'{value:.9g}'))
        self.table.resizeColumnsToContents()

    def perform(self,action):
        row=self.table.currentRow();name=self.table.item(row,0).text() if row>=0 else None
        if action!='add' and name is None:return
        if action=='delete':del self.project.joint_springs[name];self.refresh();return
        if len(self.project.nodes)<2:QMessageBox.information(self,'Joint Springs','Add two distinct joints first.');return
        nodes=list(self.project.nodes)
        spring=self.project.joint_springs[name] if action=='edit' else JointSpring(self.project.next_name('S',set(self.project.nodes)|set(self.project.members)|set(self.project.joint_springs)),nodes[0],nodes[1],1.)
        editor=JointSpringEditor(self,self.project,spring,name if action=='edit' else None)
        if editor.exec()==QDialog.DialogCode.Accepted:
            if action=='edit':del self.project.joint_springs[name]
            self.project.joint_springs[editor.definition.name]=editor.definition;self.refresh()
        editor.deleteLater()

    def accept(self):
        try:self.project.validate()
        except ValueError as error:QMessageBox.warning(self,'Joint Springs',str(error));return
        super().accept()
