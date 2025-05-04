from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QProgressBar, QLabel, QFileDialog, QTreeWidget, QTreeWidgetItem, QSplitter
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread, Signal
import os
import download_images
import re

def extract_profile_and_board(url):
    """Extract profile and board name from a Pinterest board URL."""
    # Example: https://www.pinterest.com/<profile>/<board>/
    m = re.match(r"https?://(www\.)?pinterest\.com/([^/]+)/([^/]+)/?", url)
    if m:
        return m.group(2), m.group(3)
    return None, None

def extract_profile_and_board_or_fallback(url):
    """Extract profile and board name from a Pinterest board URL, or fallback to a formatted directory name."""
    m = re.match(r"https?://(www\.|[a-z]{2}\.)?pinterest\.com/([^/]+)/([^/]+)/?", url)
    if m:
        return m.group(2), m.group(3)
    # Fallback: use the first path segment and a sanitized version of the rest
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.strip('/').split('/') if p]
        if len(path_parts) >= 2:
            return path_parts[0], path_parts[1]
        elif len(path_parts) == 1:
            # Use the domain as profile, and the path as board
            domain = parsed.netloc.split('.')[-2]
            return domain, path_parts[0]
        else:
            # Use the domain as profile, and a hash of the URL as board
            import hashlib
            domain = parsed.netloc.split('.')[-2]
            board = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
            return domain, board
    except Exception:
        # As a last resort, hash the URL
        import hashlib
        return 'unknown', hashlib.md5(url.encode('utf-8')).hexdigest()[:12]

class DownloadThread(QThread):
    progress = Signal(int)
    finished = Signal()
    error = Signal(str)

    def __init__(self, url, output_dir, quality, scroll_pause):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.quality = quality
        self.scroll_pause = scroll_pause

    def run(self):
        try:
            profile, board = extract_profile_and_board_or_fallback(self.url)
            save_dir = os.path.join(self.output_dir, profile, board)
            driver = download_images.setup_driver()
            driver.get(self.url)
            image_dict = download_images.scroll_and_collect(driver, self.scroll_pause)
            driver.quit()
            # Count total images for progress
            total = sum(len(q['high']) + len(q['low']) for q in image_dict.values())
            count = 0
            def progress_hook():
                nonlocal count
                count += 1
                percent = int((count / total) * 100) if total else 0
                self.progress.emit(percent)
            # Patch download_images.download_images to call progress_hook
            def patched_download_images(image_dict, output_dir, quality_pref):
                os.makedirs(output_dir, exist_ok=True)
                for img_id, quality_urls in image_dict.items():
                    high_quality_urls = quality_urls['high']
                    low_quality_urls = quality_urls['low']
                    urls_to_download = []
                    if quality_pref == 'high-only':
                        if high_quality_urls:
                            urls_to_download = [(list(high_quality_urls)[0], 'high')]
                    elif quality_pref == 'prioritize-high':
                        if high_quality_urls:
                            urls_to_download = [(list(high_quality_urls)[0], 'high')]
                        elif low_quality_urls:
                            urls_to_download = [(list(low_quality_urls)[0], 'low')]
                    elif quality_pref == 'all':
                        if high_quality_urls:
                            urls_to_download.append((list(high_quality_urls)[0], 'high'))
                        if low_quality_urls:
                            urls_to_download.append((list(low_quality_urls)[0], 'low'))
                    for img_url, quality in urls_to_download:
                        try:
                            resp = download_images.requests.get(img_url, timeout=10)
                            resp.raise_for_status()
                            if quality_pref == 'all':
                                fname = download_images.sanitize_filename(img_url, quality)
                            else:
                                fname = download_images.sanitize_filename(img_url)
                            path = os.path.join(output_dir, fname)
                            with open(path, "wb") as f:
                                f.write(resp.content)
                        except Exception:
                            pass
                        progress_hook()
            patched_download_images(image_dict, save_dir, self.quality)
            self.progress.emit(100)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class PinterestDownloaderWindow(QWidget):
    def __init__(self, image_dir="images"):
        super().__init__()
        self.setWindowTitle("Pinterest Board Downloader")
        self.image_dir = image_dir
        self.image_files = []
        self.current_index = 0
        self.current_folder = None
        self._setup_ui()
        self._populate_tree()
        self._load_images()
        self._update_image_viewer()

    def _setup_ui(self):
        main_layout = QHBoxLayout()
        splitter = QSplitter()

        # File tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Boards")
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        splitter.addWidget(self.tree)

        # Right side layout
        right_widget = QWidget()
        layout = QVBoxLayout()

        # Link input and Go button
        link_layout = QHBoxLayout()
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText("Paste Pinterest board URL here...")
        self.go_button = QPushButton("Go")
        link_layout.addWidget(self.link_edit)
        link_layout.addWidget(self.go_button)
        layout.addLayout(link_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Image viewer and navigation
        viewer_layout = QVBoxLayout()
        self.image_label = QLabel("No images downloaded yet.")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(300)
        viewer_layout.addWidget(self.image_label)

        nav_layout = QHBoxLayout()
        self.left_button = QPushButton("<")
        self.right_button = QPushButton(">")
        nav_layout.addWidget(self.left_button)
        nav_layout.addWidget(self.right_button)
        viewer_layout.addLayout(nav_layout)

        layout.addLayout(viewer_layout)
        right_widget.setLayout(layout)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 600])
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        # Connect navigation
        self.left_button.clicked.connect(self._show_prev_image)
        self.right_button.clicked.connect(self._show_next_image)
        self.go_button.clicked.connect(self._on_go_clicked)

    def _populate_tree(self):
        self.tree.clear()
        if not os.path.exists(self.image_dir):
            return
        for profile in sorted(os.listdir(self.image_dir)):
            profile_path = os.path.join(self.image_dir, profile)
            if not os.path.isdir(profile_path):
                continue
            profile_item = QTreeWidgetItem([profile])
            for board in sorted(os.listdir(profile_path)):
                board_path = os.path.join(profile_path, board)
                if not os.path.isdir(board_path):
                    continue
                board_item = QTreeWidgetItem([board])
                board_item.setData(0, Qt.UserRole, board_path)
                profile_item.addChild(board_item)
            self.tree.addTopLevelItem(profile_item)
        self.tree.expandAll()

    def _on_tree_item_clicked(self, item, column):
        folder = item.data(0, Qt.UserRole)
        if folder:
            self.current_folder = folder
            self._load_images()
            self._update_image_viewer()

    def _on_go_clicked(self):
        url = self.link_edit.text().strip()
        if not url:
            self.progress_bar.setFormat("Please enter a URL.")
            return
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.go_button.setEnabled(False)
        self.download_thread = DownloadThread(
            url=url,
            output_dir=self.image_dir,
            quality="high-only",
            scroll_pause=2.0
        )
        self.download_thread.progress.connect(self.progress_bar.setValue)
        self.download_thread.finished.connect(self._on_download_finished)
        self.download_thread.error.connect(self._on_download_error)
        self.download_thread.start()

    def _on_download_finished(self):
        self.go_button.setEnabled(True)
        self._populate_tree()
        self.refresh_images()
        self.progress_bar.setFormat("Done!")

    def _on_download_error(self, msg):
        self.go_button.setEnabled(True)
        self.progress_bar.setFormat(f"Error: {msg}")

    def _load_images(self):
        folder = self.current_folder or self.image_dir
        if not os.path.exists(folder):
            self.image_files = []
            return
        files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        self.image_files = sorted(files)
        self.current_index = 0

    def _update_image_viewer(self):
        folder = self.current_folder or self.image_dir
        if not self.image_files:
            self.image_label.setText("No images downloaded yet.")
            return
        img_path = os.path.join(folder, self.image_files[self.current_index])
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            self.image_label.setText(f"Cannot load image: {self.image_files[self.current_index]}")
        else:
            self.image_label.setPixmap(pixmap.scaled(500, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _show_prev_image(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self._update_image_viewer()

    def _show_next_image(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self._update_image_viewer()

    def refresh_images(self):
        self._load_images()
        self._update_image_viewer()
