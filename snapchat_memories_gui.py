#!/usr/bin/env python3
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def _display_arg(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or any(ch in "\"'" for ch in value):
        return f'"{value}"'
    return value


class DownloaderGUI(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.root_dir = Path(__file__).resolve().parent
        self.script_path = self.root_dir / "download_memories.py"
        self.process = None

        self._progress_re = re.compile(r"\[(\d+)/(\d+)\]")

        self._build_ui()
        self._connect_signals()
        self._on_merge_overlays_toggled(self.merge_overlays_checkbox.isChecked())
        self._update_mode_ui()
        self._update_command_preview()

    def _build_ui(self) -> None:
        self.setWindowTitle("Snapchat Memories Downloader (GUI)")
        self.resize(960, 820)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        self.setCentralWidget(scroll)

        layout = QVBoxLayout(container)
        layout.setSpacing(16)

        title = QLabel("Snapchat Memories Downloader GUI")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 6)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel(
            "Local desktop app for the Python downloader. Nothing is uploaded."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [
                "Download from memories_history.html",
                "Merge existing -main/-overlay files",
            ]
        )
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        self.download_group = QGroupBox("Download inputs")
        download_layout = QVBoxLayout(self.download_group)
        download_grid = QHBoxLayout()
        download_left = QVBoxLayout()
        download_right = QVBoxLayout()

        self.html_path_edit = QLineEdit()
        self.html_path_edit.setPlaceholderText(
            "Path to memories_history.html or folder containing it"
        )
        self.html_browse_button = QPushButton("Browse HTML")
        download_left.addWidget(QLabel("memories_history.html"))
        download_left.addWidget(self.html_path_edit)
        download_right.addWidget(self.html_browse_button)

        self.output_path_edit = QLineEdit("memories")
        self.output_browse_button = QPushButton("Browse Output Folder")

        download_grid.addLayout(download_left, 1)
        download_grid.addLayout(download_right)
        download_layout.addLayout(download_grid)

        def help_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setWordWrap(True)
            label.setStyleSheet("color: #555;")
            label.setContentsMargins(24, 0, 0, 6)
            return label

        output_layout = QHBoxLayout()
        output_left = QVBoxLayout()
        output_left.addWidget(QLabel("Output folder"))
        output_left.addWidget(self.output_path_edit)
        output_layout.addLayout(output_left, 1)
        output_layout.addWidget(self.output_browse_button)
        download_layout.addLayout(output_layout)

        download_note = QLabel(
            "The output folder will contain your files plus metadata.json for resume/retry."
        )
        download_note.setWordWrap(True)
        download_layout.addWidget(download_note)
        layout.addWidget(self.download_group)

        self.merge_group = QGroupBox("Merge existing overlay pairs")
        merge_layout = QVBoxLayout(self.merge_group)
        merge_row = QHBoxLayout()
        self.merge_folder_edit = QLineEdit()
        self.merge_folder_edit.setPlaceholderText(
            "Folder with -main and -overlay files"
        )
        self.merge_browse_button = QPushButton("Browse Folder")
        merge_row.addWidget(self.merge_folder_edit, 1)
        merge_row.addWidget(self.merge_browse_button)
        merge_layout.addWidget(QLabel("Folder"))
        merge_layout.addLayout(merge_row)
        merge_note = QLabel(
            "This creates merged files next to the originals and does not delete -main/-overlay files."
        )
        merge_note.setWordWrap(True)
        merge_layout.addWidget(merge_note)
        layout.addWidget(self.merge_group)

        self.run_mode_group = QGroupBox("Run mode")
        run_layout = QVBoxLayout(self.run_mode_group)
        self.resume_checkbox = QCheckBox("Resume interrupted download")
        self.retry_failed_checkbox = QCheckBox("Retry failed downloads only")
        self.test_checkbox = QCheckBox("Test mode (first 3 items only)")
        run_layout.addWidget(self.resume_checkbox)
        run_layout.addWidget(
            help_label("Uses metadata.json to continue pending or failed items.")
        )
        run_layout.addWidget(self.retry_failed_checkbox)
        run_layout.addWidget(
            help_label("Only re-download items marked as failed in metadata.json.")
        )
        run_layout.addWidget(self.test_checkbox)
        run_layout.addWidget(
            help_label("Quick check for dependencies. Ignores filters like videos-only.")
        )

        threads_row = QHBoxLayout()
        threads_label = QLabel("Parallel downloads")
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 16)
        self.threads_spin.setValue(1)
        threads_row.addWidget(threads_label)
        threads_row.addWidget(self.threads_spin)
        threads_row.addStretch(1)
        run_layout.addLayout(threads_row)
        run_layout.addWidget(
            help_label("Higher values use more bandwidth/CPU. Set to 1 for sequential.")
        )
        layout.addWidget(self.run_mode_group)

        self.filter_group = QGroupBox("Filters")
        filter_layout = QVBoxLayout(self.filter_group)
        self.videos_only_checkbox = QCheckBox("Videos only")
        self.pictures_only_checkbox = QCheckBox("Pictures only")
        self.overlays_only_checkbox = QCheckBox("Overlays only")
        filter_layout.addWidget(self.videos_only_checkbox)
        filter_layout.addWidget(help_label("Download and process only video memories."))
        filter_layout.addWidget(self.pictures_only_checkbox)
        filter_layout.addWidget(help_label("Download and process only image memories."))
        filter_layout.addWidget(self.overlays_only_checkbox)
        filter_layout.addWidget(
            help_label("Skip memories without overlays (only ZIP overlay items).")
        )
        layout.addWidget(self.filter_group)

        self.overlay_group = QGroupBox("Overlay processing")
        overlay_layout = QVBoxLayout(self.overlay_group)
        self.merge_overlays_checkbox = QCheckBox("Merge overlays")
        self.defer_video_overlays_checkbox = QCheckBox(
            "Process video overlays at the end"
        )
        overlay_layout.addWidget(self.merge_overlays_checkbox)
        overlay_layout.addWidget(
            help_label("Combine -main and -overlay into one file. Videos require FFmpeg.")
        )
        overlay_layout.addWidget(self.defer_video_overlays_checkbox)
        overlay_layout.addWidget(
            help_label("Download everything first, then merge videos. Requires merge overlays.")
        )
        layout.addWidget(self.overlay_group)

        self.naming_group = QGroupBox("Naming")
        naming_layout = QVBoxLayout(self.naming_group)
        self.timestamp_filenames_checkbox = QCheckBox("Timestamp-based filenames")
        naming_layout.addWidget(self.timestamp_filenames_checkbox)
        naming_layout.addWidget(
            help_label("Use YYYY.MM.DD-HH-MM-SS.ext instead of sequential numbers (Windows-safe).")
        )
        layout.addWidget(self.naming_group)

        self.extra_group = QGroupBox("Post-processing")
        extra_layout = QVBoxLayout(self.extra_group)
        self.remove_duplicates_checkbox = QCheckBox("Remove duplicates during download")
        self.join_multi_snaps_checkbox = QCheckBox("Join multi-snap videos")
        extra_layout.addWidget(self.remove_duplicates_checkbox)
        extra_layout.addWidget(
            help_label("Skips duplicates using size and MD5 hash checks.")
        )
        extra_layout.addWidget(self.join_multi_snaps_checkbox)
        extra_layout.addWidget(
            help_label("Joins videos captured within 10 seconds (requires FFmpeg).")
        )
        layout.addWidget(self.extra_group)

        notes = QLabel(
            "Notes: FFmpeg is required for video overlay merging and multi-snap joins. "
            "Pillow is required for image overlay merging."
        )
        notes.setWordWrap(True)
        layout.addWidget(notes)

        command_label = QLabel("Command preview")
        layout.addWidget(command_label)
        self.command_preview = QPlainTextEdit()
        self.command_preview.setReadOnly(True)
        self.command_preview.setMaximumHeight(70)
        layout.addWidget(self.command_preview)

        button_row = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.clear_button = QPushButton("Clear logs")
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        button_row.addWidget(self.clear_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        status_row = QHBoxLayout()
        self.status_label = QLabel("Idle")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.progress_bar, 1)
        layout.addLayout(status_row)

        log_label = QLabel("Logs")
        layout.addWidget(log_label)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(2000)
        layout.addWidget(self.log_output)

    def _connect_signals(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._update_mode_ui)
        self.mode_combo.currentIndexChanged.connect(self._update_command_preview)
        self.html_browse_button.clicked.connect(self._choose_html_file)
        self.output_browse_button.clicked.connect(self._choose_output_folder)
        self.merge_browse_button.clicked.connect(self._choose_merge_folder)
        self.start_button.clicked.connect(self._start_process)
        self.stop_button.clicked.connect(self._stop_process)
        self.clear_button.clicked.connect(self.log_output.clear)

        self.html_path_edit.textChanged.connect(self._update_command_preview)
        self.output_path_edit.textChanged.connect(self._update_command_preview)
        self.merge_folder_edit.textChanged.connect(self._update_command_preview)

        for checkbox in [
            self.resume_checkbox,
            self.retry_failed_checkbox,
            self.test_checkbox,
            self.merge_overlays_checkbox,
            self.defer_video_overlays_checkbox,
            self.videos_only_checkbox,
            self.pictures_only_checkbox,
            self.overlays_only_checkbox,
            self.timestamp_filenames_checkbox,
            self.remove_duplicates_checkbox,
            self.join_multi_snaps_checkbox,
        ]:
            checkbox.toggled.connect(self._update_command_preview)

        self.threads_spin.valueChanged.connect(self._update_command_preview)

        self.resume_checkbox.toggled.connect(self._on_resume_toggled)
        self.retry_failed_checkbox.toggled.connect(self._on_retry_toggled)
        self.test_checkbox.toggled.connect(self._on_test_toggled)
        self.videos_only_checkbox.toggled.connect(self._on_videos_only_toggled)
        self.pictures_only_checkbox.toggled.connect(self._on_pictures_only_toggled)
        self.merge_overlays_checkbox.toggled.connect(self._on_merge_overlays_toggled)

    def _update_mode_ui(self) -> None:
        download_mode = self.mode_combo.currentIndex() == 0
        self.download_group.setVisible(download_mode)
        self.run_mode_group.setVisible(download_mode)
        self.filter_group.setVisible(download_mode)
        self.overlay_group.setVisible(download_mode)
        self.naming_group.setVisible(download_mode)
        self.extra_group.setVisible(download_mode)
        self.merge_group.setVisible(not download_mode)

    def _choose_html_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select memories_history.html",
            str(self.root_dir),
            "HTML files (*.html);;All files (*)",
        )
        if file_path:
            self.html_path_edit.setText(file_path)

    def _choose_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", str(self.root_dir)
        )
        if folder:
            self.output_path_edit.setText(folder)

    def _choose_merge_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder with -main/-overlay files", str(self.root_dir)
        )
        if folder:
            self.merge_folder_edit.setText(folder)

    def _on_resume_toggled(self, checked: bool) -> None:
        if checked:
            self.retry_failed_checkbox.setChecked(False)
            self.test_checkbox.setChecked(False)

    def _on_retry_toggled(self, checked: bool) -> None:
        if checked:
            self.resume_checkbox.setChecked(False)
            self.test_checkbox.setChecked(False)

    def _on_test_toggled(self, checked: bool) -> None:
        if checked:
            self.resume_checkbox.setChecked(False)
            self.retry_failed_checkbox.setChecked(False)

    def _on_videos_only_toggled(self, checked: bool) -> None:
        if checked:
            self.pictures_only_checkbox.setChecked(False)

    def _on_pictures_only_toggled(self, checked: bool) -> None:
        if checked:
            self.videos_only_checkbox.setChecked(False)

    def _on_merge_overlays_toggled(self, checked: bool) -> None:
        self.defer_video_overlays_checkbox.setEnabled(checked)
        if not checked:
            self.defer_video_overlays_checkbox.setChecked(False)

    def _build_args(self) -> list:
        args = []
        if self.mode_combo.currentIndex() == 1:
            merge_folder = self.merge_folder_edit.text().strip()
            if merge_folder:
                args.extend(["--merge-existing", merge_folder])
            return args

        html_path = self.html_path_edit.text().strip()
        if html_path:
            args.append(html_path)

        output_dir = self.output_path_edit.text().strip()
        if output_dir:
            args.extend(["-o", output_dir])

        if self.resume_checkbox.isChecked():
            args.append("--resume")
        if self.retry_failed_checkbox.isChecked():
            args.append("--retry-failed")
        if self.test_checkbox.isChecked():
            args.append("--test")
        if self.merge_overlays_checkbox.isChecked():
            args.append("--merge-overlays")
        if self.defer_video_overlays_checkbox.isChecked():
            args.append("--defer-video-overlays")
        if self.videos_only_checkbox.isChecked():
            args.append("--videos-only")
        if self.pictures_only_checkbox.isChecked():
            args.append("--pictures-only")
        if self.overlays_only_checkbox.isChecked():
            args.append("--overlays-only")
        if self.timestamp_filenames_checkbox.isChecked():
            args.append("--timestamp-filenames")
        if self.remove_duplicates_checkbox.isChecked():
            args.append("--remove-duplicates")
        if self.join_multi_snaps_checkbox.isChecked():
            args.append("--join-multi-snaps")
        if self.threads_spin.value() > 1:
            args.extend(["--threads", str(self.threads_spin.value())])

        return args

    def _update_command_preview(self) -> None:
        args = self._build_args()
        command = [sys.executable, "-u", str(self.script_path)] + args
        preview = " ".join(_display_arg(arg) for arg in command)
        self.command_preview.setPlainText(preview)

    def _append_log(self, text: str) -> None:
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.log_output.setTextCursor(cursor)

    def _maybe_update_progress(self, line: str) -> None:
        match = self._progress_re.search(line)
        if not match:
            return
        current, total = int(match.group(1)), int(match.group(2))
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Processing {current} of {total}")

    def _start_process(self) -> None:
        if not self.script_path.exists():
            QMessageBox.critical(
                self,
                "Missing script",
                f"Could not find {self.script_path}.",
            )
            return

        download_mode = self.mode_combo.currentIndex() == 0
        if download_mode:
            html_path = self.html_path_edit.text().strip()
            if not html_path:
                QMessageBox.warning(
                    self, "Missing HTML", "Please select memories_history.html."
                )
                return
            if not Path(html_path).exists():
                QMessageBox.warning(
                    self, "Missing file", "The selected HTML path does not exist."
                )
                return

            output_dir = self.output_path_edit.text().strip() or "memories"
            metadata_path = Path(output_dir) / "metadata.json"
            if (self.resume_checkbox.isChecked() or self.retry_failed_checkbox.isChecked()) and not metadata_path.exists():
                self._append_log(
                    "Warning: metadata.json not found in output folder; resume/retry may fail.\n"
                )
        else:
            merge_folder = self.merge_folder_edit.text().strip()
            if not merge_folder:
                QMessageBox.warning(
                    self, "Missing folder", "Please select a folder to merge."
                )
                return
            if not Path(merge_folder).is_dir():
                QMessageBox.warning(
                    self, "Invalid folder", "The selected folder does not exist."
                )
                return

        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, "Already running", "A process is already running.")
            return

        args = ["-u", str(self.script_path)] + self._build_args()

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(self.root_dir))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._handle_process_output)
        self.process.finished.connect(self._handle_process_finished)

        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Running...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self._append_log("Starting process...\n")
        self.process.start(sys.executable, args)

    def _stop_process(self) -> None:
        if not self.process:
            return
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.process.terminate()
        if not self.process.waitForFinished(2000):
            self.process.kill()
        self._append_log("Process stopped by user.\n")

    def _handle_process_output(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if not data:
            return
        self._append_log(data)
        for line in data.splitlines():
            self._maybe_update_progress(line)

    def _handle_process_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText(f"Finished (exit code {exit_code})")
        self._append_log(f"Process finished with exit code {exit_code}.\n")


def main() -> int:
    app = QApplication(sys.argv)
    window = DownloaderGUI()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
