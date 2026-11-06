"""Controls shared by the Alerts and Overlay styles pages: every fine-detail option, your own saved styles, import, export and reset."""
import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSlider, QSpinBox, QWidget)

from . import style_fields as fields
from .ui_kit import field_row, hrow, section_card

CARD_TABS = {"Background and frame": "Box", "Text detail": "Text", "Motion and place": "Box", "Custom CSS": "Custom CSS"}
FILE_FILTER = "CHATDOOM style (*.json)"


def _number(low, high):
    """A slider with the exact number beside it."""
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    slider = QSlider(Qt.Horizontal)
    slider.setRange(low, high)
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setFixedWidth(84)
    slider.valueChanged.connect(spin.setValue)
    spin.valueChanged.connect(slider.setValue)
    row.addWidget(slider, 1)
    row.addWidget(spin)
    holder.spin = spin
    return holder


class DesignTools:
    """Mixed into a SubPage that has design(), _set(), _apply(), load() and tool_kind()."""

    def add_design_tools(self, kinds, extra_tab="Layout"):
        self.field_widgets, self.field_cards = {}, []
        kind_cards = {}
        for row in fields.FIELDS:
            if set(row[6]) & set(kinds):
                kind_cards.setdefault(row[7], []).append(row)
        self.add_tab("Box")
        self.add_tab("Custom CSS")
        self.add_tab("My styles")
        for card, rows in kind_cards.items():
            lay = self._layouts[self._names.index(CARD_TABS.get(card, extra_tab))]
            c, cl = section_card(card, "")
            for row in rows:
                cl.addWidget(self._detail_field(row))
            lay.addWidget(c)
            self.field_cards.append((set(k for r in rows for k in r[6]), c))
        self._build_my_styles(self._layouts[self._names.index("My styles")])

    def _detail_field(self, row):
        key, kind_of, _default, label, note, extra, _kinds, _card = row
        if kind_of == "flag":
            box = QCheckBox(label)
            box.toggled.connect(lambda on: self._set(key, on))
            self.field_widgets[key] = (kind_of, box)
            return box
        if kind_of == "choice":
            widget = QComboBox()
            for text, value in extra:
                widget.addItem(text, value)
            widget.currentIndexChanged.connect(lambda _: self._set(key, widget.currentData()))
        elif kind_of == "num":
            widget = _number(*extra)
            widget.spin.valueChanged.connect(lambda v: self._set(key, v))
        elif kind_of == "color":
            widget = QPushButton()
            widget.setFixedSize(70, 30)
            widget.clicked.connect(lambda _=False: self._choose_colour(key))
        elif kind_of == "text":
            widget = QLineEdit()
            widget.setMaxLength(extra)
            widget.editingFinished.connect(lambda: self._set(key, widget.text().strip()))
        else:
            widget = QPlainTextEdit()
            widget.setMinimumHeight(220)
            widget.setPlaceholderText(".m b { color: gold; }")
            save = QPushButton("Save CSS")
            save.setObjectName("primary")
            save.clicked.connect(lambda _=False: self._set(key, widget.toPlainText()[:extra]))
            self.field_widgets[key] = (kind_of, widget)
            holder = QWidget()
            holder_lay = QHBoxLayout(holder)
            holder_lay.setContentsMargins(0, 0, 0, 0)
            holder_lay.addWidget(field_row(label, note, widget), 1)
            holder_lay.addWidget(save, 0, Qt.AlignBottom)
            return holder
        self.field_widgets[key] = (kind_of, widget)
        return field_row(label, note, widget)

    def _choose_colour(self, key):
        colour = QColorDialog.getColor(QColor(self.design()[key]), self, "Choose a colour")
        if colour.isValid():
            self._set(key, colour.name())

    def load_design_tools(self, design):
        kind = self.tool_kind()
        for key, (kind_of, widget) in self.field_widgets.items():
            if key not in design:
                continue
            value = design[key]
            if kind_of == "flag":
                widget.setChecked(value)
            elif kind_of == "choice":
                widget.setCurrentIndex(max(0, widget.findData(value)))
            elif kind_of == "num":
                widget.spin.setValue(value)
            elif kind_of == "color":
                widget.setStyleSheet("background:%s;border-radius:8px;" % value)
            elif kind_of == "text":
                if widget.text() != value:
                    widget.setText(value)
            elif widget.toPlainText() != value:
                widget.setPlainText(value)
        for kinds, card in self.field_cards:
            card.setVisible(kind in kinds)
        self._refresh_my_styles()

    # ---------- your own styles ----------
    def _build_my_styles(self, lay):
        c, cl = section_card("My styles", "Save the design you are editing and bring it back with one click. Files can be shared with other streamers.")
        self.my_list = QComboBox()
        apply_btn, delete_btn = QPushButton("Use this style"), QPushButton("Delete")
        apply_btn.setObjectName("primary")
        delete_btn.setObjectName("quiet")
        apply_btn.clicked.connect(self.use_my_style)
        delete_btn.clicked.connect(self.delete_my_style)
        save_btn = QPushButton("Save current design")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._ask_style_name)
        cl.addWidget(field_row("Saved styles", "", self.my_list))
        cl.addWidget(hrow(apply_btn, delete_btn, save_btn))
        export_btn, import_btn, reset_btn = QPushButton("Export to a file"), QPushButton("Import from a file"), QPushButton("Reset to default")
        for b in (export_btn, import_btn, reset_btn):
            b.setObjectName("quiet")
        export_btn.clicked.connect(self._export_style)
        import_btn.clicked.connect(self._import_style)
        reset_btn.clicked.connect(self.reset_design)
        cl.addWidget(hrow(export_btn, import_btn, reset_btn))
        self.my_note = QLabel("")
        self.my_note.setObjectName("settingNote")
        cl.addWidget(self.my_note)
        lay.addWidget(c)

    def _my_styles(self):
        saved = self.s.get("ov_my_styles")
        saved = dict(saved) if isinstance(saved, dict) else {}
        items = saved.get(self.tool_kind())
        return saved, [dict(i) for i in items if isinstance(i, dict) and i.get("name")] if isinstance(items, list) else []

    def _refresh_my_styles(self):
        keep = self.my_list.currentText()
        self.my_list.clear()
        for item in self._my_styles()[1]:
            self.my_list.addItem(item["name"])
        self.my_list.setCurrentIndex(max(0, self.my_list.findText(keep)))

    def save_my_style(self, name):
        name = (name or "").strip()[:40]
        if not name:
            return False
        saved, items = self._my_styles()
        items = [i for i in items if i["name"] != name]
        if len(items) >= fields.MAX_MY_STYLES:
            self.my_note.setText("You can keep %d styles here. Delete one first." % fields.MAX_MY_STYLES)
            return False
        items.append({"name": name, "design": self.design()})
        saved[self.tool_kind()] = items
        self.s.set("ov_my_styles", saved)
        self._refresh_my_styles()
        self.my_list.setCurrentIndex(self.my_list.findText(name))
        self.my_note.setText("Saved %s." % name)
        return True

    def _ask_style_name(self):
        name, ok = QInputDialog.getText(self, "Save this style", "Name")
        if ok:
            self.save_my_style(name)

    def use_my_style(self):
        item = next((i for i in self._my_styles()[1] if i["name"] == self.my_list.currentText()), None)
        if item:
            self._apply(item.get("design") or {})

    def delete_my_style(self):
        saved, items = self._my_styles()
        saved[self.tool_kind()] = [i for i in items if i["name"] != self.my_list.currentText()]
        self.s.set("ov_my_styles", saved)
        self._refresh_my_styles()

    def export_style(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"chatdoomStyle": 1, "kind": self.tool_kind(), "design": self.design()}, f, ensure_ascii=False, indent=1)

    def import_style(self, path):
        """Only a real style file for this overlay is taken, and every value in it is checked when it is saved."""
        try:
            if os.path.getsize(path) > 200000:
                raise ValueError
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("chatdoomStyle") != 1 or not isinstance(data.get("design"), dict):
                raise ValueError
        except (OSError, ValueError, AttributeError):
            self.my_note.setText("That is not a CHATDOOM style file.")
            return False
        if data.get("kind") != self.tool_kind():
            self.my_note.setText("That style is for a different overlay. Choose that overlay first.")
            return False
        self._apply(data["design"])
        self.my_note.setText("Style imported.")
        return True

    def _export_style(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export style", os.path.expanduser("~/%s-style.json" % self.tool_kind()), FILE_FILTER)
        if path:
            self.export_style(path)
            self.my_note.setText("Exported.")

    def _import_style(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import style", os.path.expanduser("~"), FILE_FILTER)
        if path:
            self.import_style(path)
