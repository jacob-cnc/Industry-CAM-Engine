import FreeCADGui as Gui
import FreeCAD as App
from PySide import QtCore, QtGui
from BaptTools import ToolDatabase, Tool


class ToolSelectorDialog(QtGui.QDialog):
    """Dialogue pour sélectionner un outil"""

    def __init__(self, current_tool_id=-1, parent=None):
        super(ToolSelectorDialog, self).__init__(parent)
        self.current_tool_id = current_tool_id
        self.selected_tool_id = -1
        self.selected_tool_name = ""
        self.selected_tool = None
        self.setup_ui()
        self.load_tools()

    def setup_ui(self):
        """Configure l'interface utilisateur"""
        self.setWindowTitle("Sélectionner un outil")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        layout = QtGui.QVBoxLayout(self)

        # Filtre pour les outils
        filter_layout = QtGui.QHBoxLayout()

        # Filtre par texte
        filter_label = QtGui.QLabel("Filtre texte:")
        self.filter_edit = QtGui.QLineEdit()
        self.filter_edit.textChanged.connect(self.filter_tools)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_edit)

        # Filtre par type d'outil
        type_label = QtGui.QLabel("Type d'outil:")
        self.type_combo = QtGui.QComboBox()
        self.type_combo.addItem("Tous", "")
        # Les types seront ajoutés dynamiquement lors du chargement des outils
        self.type_combo.currentIndexChanged.connect(self.filter_tools)
        filter_layout.addWidget(type_label)
        filter_layout.addWidget(self.type_combo)

        layout.addLayout(filter_layout)

        # Table des outils
        self.tool_table = QtGui.QTableWidget()
        self.tool_table.setColumnCount(5)
        self.tool_table.setHorizontalHeaderLabels(["ID", "Nom", "Type", "Diamètre", "Longueur"])
        self.tool_table.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
        self.tool_table.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
        self.tool_table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.tool_table.horizontalHeader().setStretchLastSection(True)
        self.tool_table.doubleClicked.connect(self.accept)

        layout.addWidget(self.tool_table)

        # Boutons d'action
        button_layout = QtGui.QHBoxLayout()

        # Bouton pour ajouter un outil
        self.add_tool_button = QtGui.QPushButton("Ajouter un outil")
        self.add_tool_button.clicked.connect(self.add_tool)
        button_layout.addWidget(self.add_tool_button)

        # Spacer pour pousser les boutons OK/Annuler à droite
        button_layout.addStretch()

        # Boutons standard
        button_box = QtGui.QDialogButtonBox(
            QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

    def load_tools(self):
        """Charge les outils depuis la base de données"""
        try:
            # Récupérer les outils
            db = ToolDatabase()
            self.tools = db.get_all_tools()

            # Ajouter les types d'outils au combobox
            types = set(tool.type for tool in self.tools)
            for tool_type in types:
                self.type_combo.addItem(tool_type, tool_type)

            # Remplir la table
            self.update_tool_table(self.tools)

            # Sélectionner l'outil actuel si défini
            if self.current_tool_id >= 0:
                for row in range(self.tool_table.rowCount()):
                    if int(self.tool_table.item(row, 0).text()) == self.current_tool_id:
                        self.tool_table.selectRow(row)
                        break
        except Exception as e:
            App.Console.PrintError(f"Erreur lors du chargement des outils: {str(e)}\n")

    def update_tool_table(self, tools):
        """Met à jour la table des outils avec la liste fournie"""
        self.tool_table.setRowCount(0)

        for tool in tools:
            row = self.tool_table.rowCount()
            self.tool_table.insertRow(row)

            # Ajouter les données de l'outil
            self.tool_table.setItem(row, 0, QtGui.QTableWidgetItem(str(tool.id)))
            self.tool_table.setItem(row, 1, QtGui.QTableWidgetItem(tool.name))
            self.tool_table.setItem(row, 2, QtGui.QTableWidgetItem(tool.type))
            self.tool_table.setItem(row, 3, QtGui.QTableWidgetItem(f"{tool.diameter:.2f} mm"))
            self.tool_table.setItem(row, 4, QtGui.QTableWidgetItem(f"{tool.length:.2f} mm"))

        # Ajuster les colonnes
        self.tool_table.resizeColumnsToContents()

    def filter_tools(self):
        """Filtre les outils en fonction du texte saisi"""
        filter_text = self.filter_edit.text().lower()
        selected_type = self.type_combo.currentData()

        if not filter_text and selected_type == "":
            # Aucun filtre, afficher tous les outils
            self.update_tool_table(self.tools)
            return

        # Filtrer les outils
        filtered_tools = [tool for tool in self.tools if
                          (filter_text in tool.name.lower()
                           or filter_text in tool.type.lower()
                           or filter_text in str(tool.diameter)) and
                          (selected_type == "" or tool.type == selected_type)]

        # Mettre à jour la table
        self.update_tool_table(filtered_tools)

    def add_tool(self):
        """Ouvre le dialogue pour ajouter un nouvel outil"""
        from BaptTools import ToolDialog
        dialog = ToolDialog(parent=self)
        result = dialog.exec_()

        if result == QtGui.QDialog.Accepted:
            # Ajouter l'outil à la base de données
            try:
                db = ToolDatabase()
                db.add_tool(dialog.tool)

                # Recharger la liste des outils
                self.load_tools()

                # Sélectionner le nouvel outil
                for row in range(self.tool_table.rowCount()):
                    if self.tool_table.item(row, 1).text() == dialog.tool.name:
                        self.tool_table.selectRow(row)
                        break

                App.Console.PrintMessage(f"Outil '{dialog.tool.name}' ajouté avec succès\n")
            except Exception as e:
                App.Console.PrintError(f"Erreur lors de l'ajout de l'outil: {str(e)}\n")

    def accept(self):
        """Valider la sélection"""
        selected_items = self.tool_table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            self.selected_tool_id = int(self.tool_table.item(row, 0).text())
            self.selected_tool_name = self.tool_table.item(row, 1).text()
            db = ToolDatabase()
            self.selected_tool = db.get_tool_by_id(self.selected_tool_id)
            super(ToolSelectorDialog, self).accept()
        else:
            # Aucune sélection, ne rien faire
            pass
