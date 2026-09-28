"""Command line CAD/CAE in stile AutoCAD, sopra le stesse operazioni usate dalla GUI.

Il widget non contiene un secondo motore CAD: riceve un registro di comandi
dal MainWindow e invoca gli stessi callable usati da menu, toolbar e contesti.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable, Dict, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    callback: Callable[[list[str]], object]
    description: str = ""
    usage: str = ""
    aliases: tuple[str, ...] = ()


def tokenize_command(text: str) -> list[str]:
    """Tokenizza un comando rispettando virgolette e path con spazi."""
    return shlex.split(str(text or "").strip(), posix=False)


class CommandLineEdit(QLineEdit):
    escape_pressed = Signal()
    up_pressed = Signal()
    down_pressed = Signal()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        if event.key() == Qt.Key_Up:
            self.up_pressed.emit()
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            self.down_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CommandLineWidget(QWidget):
    """Prompt, history e autocompletamento per i comandi CAD/CAE."""

    command_issued = Signal(str)
    command_finished = Signal(str, bool, str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._commands: Dict[str, CommandSpec] = {}
        self._history: list[str] = []
        self._history_index = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 3, 4, 3)

        self.header = QLabel("<b>Command line</b> · CAD / Mesh / CAE")
        layout.addWidget(self.header)

        row = QHBoxLayout()
        self.state_label = QLabel("Pronto")
        self.state_label.setMinimumWidth(120)
        row.addWidget(self.state_label)

        row.addWidget(QLabel("Command:"))
        self.input = CommandLineEdit()
        self.input.setFont(QFont("Monospace", 10))
        self.input.setPlaceholderText(
            "POINT 0 0 0  |  MOVE 10 0 0  |  SELECT TYPE FACE  |  MESH IMPORT file.msh"
        )
        self.input.returnPressed.connect(self._submit)
        self.input.escape_pressed.connect(self.cancel_current)
        self.input.up_pressed.connect(lambda: self._history_move(-1))
        self.input.down_pressed.connect(lambda: self._history_move(1))
        row.addWidget(self.input, 1)
        layout.addLayout(row)

        self.history_view = QListWidget()
        self.history_view.setMaximumHeight(90)
        self.history_view.setAlternatingRowColors(True)
        layout.addWidget(self.history_view)

    def set_commands(self, specs: Iterable[CommandSpec]):
        self._commands.clear()
        for spec in specs:
            canonical = spec.name.strip().upper()
            self._commands[canonical] = spec
            for alias in spec.aliases:
                self._commands[alias.strip().upper()] = spec

        names = sorted({spec.name.upper() for spec in self._commands.values()})
        completer = QCompleter(names, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.input.setCompleter(completer)

    @property
    def commands(self) -> Dict[str, CommandSpec]:
        return dict(self._commands)

    def focus_input(self):
        self.input.setFocus()
        self.input.selectAll()

    def set_state(self, text: str):
        self.state_label.setText(str(text))

    def _history_move(self, delta: int):
        if not self._history:
            return
        self._history_index = max(
            0, min(len(self._history), self._history_index + int(delta))
        )
        if self._history_index >= len(self._history):
            self.input.clear()
        else:
            self.input.setText(self._history[self._history_index])
            self.input.end(False)

    def _record_history(self, text: str):
        value = str(text).strip()
        if not value:
            return
        if not self._history or self._history[-1] != value:
            self._history.append(value)
            if len(self._history) > 100:
                self._history.pop(0)
        self._history_index = len(self._history)
        item = QListWidgetItem(value)
        self.history_view.addItem(item)
        while self.history_view.count() > 50:
            self.history_view.takeItem(0)
        self.history_view.scrollToBottom()

    def _submit(self):
        text = self.input.text().strip()
        if not text:
            return
        self._record_history(text)
        self.command_issued.emit(text)

    def execute(self, text: str) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return True
        try:
            tokens = tokenize_command(raw)
        except ValueError as exc:
            self.command_finished.emit(raw, False, str(exc))
            self.set_state("Errore sintassi")
            return False

        if not tokens:
            return True

        name = tokens[0].upper()
        spec = self._commands.get(name)
        if spec is None:
            message = (
                f"Comando sconosciuto: {tokens[0]}. "
                f"Usa HELP per l'elenco dei comandi."
            )
            self.command_finished.emit(raw, False, message)
            self.set_state("Comando sconosciuto")
            return False

        self.set_state(f"Esecuzione: {spec.name}")
        try:
            result = spec.callback(tokens[1:])
            ok = result is not False
            message = "" if result is None else str(result)
            self.command_finished.emit(raw, ok, message)
            self.set_state("Completato" if ok else "Fallito")
            return bool(ok)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.command_finished.emit(raw, False, message)
            self.set_state("Fallito")
            return False
        finally:
            self.input.clear()

    def cancel_current(self):
        self.input.clear()
        self.set_state("Annullato")
        self.cancelled.emit()
