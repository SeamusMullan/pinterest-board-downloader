from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QProgressBar, QLabel, QFileDialog, QTreeWidget, QTreeWidgetItem, QSplitter, QListWidget, QListWidgetItem, QSizePolicy, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QToolBar
)
from PySide6.QtGui import QPixmap, QIcon, QWheelEvent, QMouseEvent, QAction
from PySide6.QtCore import Qt, QThread, Signal, QSize
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

class ThumbnailLoader(QThread):
    thumbnail_ready = Signal(int, QIcon)
    finished = Signal()

    def __init__(self, image_paths, size=QSize(80, 80)):
        super().__init__()
        self.image_paths = image_paths
        self.size = size
        self._is_running = True

    def run(self):
        for idx, img_path in enumerate(self.image_paths):
            if not self._is_running:
                break
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                icon = QIcon(pixmap.scaled(self.size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.thumbnail_ready.emit(idx, icon)
        self.finished.emit()

    def stop(self):
        self._is_running = False

class ImageViewer(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene().addItem(self.pixmap_item)
        from PySide6.QtGui import QPainter
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.NoDrag)
        self._zoom = 1.0
        self._panning = False
        self._pan_start = None

    def set_image(self, pixmap):
        self.scene().setSceneRect(0, 0, pixmap.width(), pixmap.height())
        self.pixmap_item.setPixmap(pixmap)
        self.reset_zoom()

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.25 if angle > 0 else 0.8
            self.zoom(factor)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier:
            self._panning = True
            self.setCursor(Qt.ClosedHandCursor)
            self._pan_start = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning and self._pan_start:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    def zoom(self, factor):
        self._zoom *= factor
        self.scale(factor, factor)

    def zoom_in(self):
        self.zoom(1.25)

    def zoom_out(self):
        self.zoom(0.8)

    def reset_zoom(self):
        self.setTransform(self.transform().fromScale(1, 1).inverted()[0])
        self._zoom = 1.0

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

        # Right side layout (main viewer + minimap)
        right_splitter = QSplitter()
        right_splitter.setOrientation(Qt.Horizontal)

        # Main viewer area
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

        # Image viewer
        self.image_viewer = ImageViewer()
        self.image_viewer.setMinimumHeight(300)
        layout.addWidget(self.image_viewer)

        # Zoom toolbar
        toolbar = QToolBar()
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.triggered.connect(self.image_viewer.zoom_in)
        toolbar.addAction(zoom_in_action)
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.triggered.connect(self.image_viewer.zoom_out)
        toolbar.addAction(zoom_out_action)
        reset_action = QAction("Reset Zoom", self)
        reset_action.triggered.connect(self.image_viewer.reset_zoom)
        toolbar.addAction(reset_action)
        layout.addWidget(toolbar)

        right_widget.setLayout(layout)
        right_splitter.addWidget(right_widget)

        # Minimap (thumbnail list)
        self.minimap = QListWidget()
        self.minimap.setViewMode(QListWidget.IconMode)
        self.minimap.setIconSize(QPixmap(80, 80).size())
        self.minimap.setResizeMode(QListWidget.Adjust)
        self.minimap.setMovement(QListWidget.Static)
        self.minimap.setSpacing(4)
        self.minimap.setMaximumWidth(100)
        self.minimap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.minimap.itemClicked.connect(self._on_minimap_item_clicked)
        right_splitter.addWidget(self.minimap)
        right_splitter.setSizes([600, 100])

        splitter.addWidget(right_splitter)
        splitter.setSizes([200, 700])
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        # Connect navigation
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
        files = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))]
        self.image_files = sorted(files)
        self.current_index = 0
        self._start_thumbnail_loading()

    def _start_thumbnail_loading(self):
        self.minimap.clear()
        if hasattr(self, 'thumbnail_loader') and self.thumbnail_loader is not None:
            self.thumbnail_loader.stop()
            self.thumbnail_loader.wait()
        folder = self.current_folder or self.image_dir
        image_paths = [os.path.join(folder, fname) for fname in self.image_files]
        self.thumbnail_loader = ThumbnailLoader(image_paths)
        self.thumbnail_loader.thumbnail_ready.connect(self._add_minimap_item)
        self.thumbnail_loader.finished.connect(self._on_thumbnails_finished)
        self.thumbnail_loader.start()

    def _add_minimap_item(self, idx, icon):
        item = QListWidgetItem(icon, "")
        item.setData(Qt.UserRole, idx)
        self.minimap.addItem(item)
        if idx == self.current_index:
            self.minimap.setCurrentRow(self.current_index)

    def _on_thumbnails_finished(self):
        pass  # Optionally handle when all thumbnails are loaded

    def _on_minimap_item_clicked(self, item):
        idx = item.data(Qt.UserRole)
        if idx is not None:
            self.current_index = idx
            self._update_image_viewer()

    def _update_image_viewer(self):
        folder = self.current_folder or self.image_dir
        if not self.image_files:
            self.image_viewer.set_image(QPixmap())
            self.minimap.clear()
            return
        img_path = os.path.join(folder, self.image_files[self.current_index])
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            self.image_viewer.set_image(QPixmap())
        else:
            self.image_viewer.set_image(pixmap)
        self.minimap.setCurrentRow(self.current_index)

    def refresh_images(self):
        self._load_images()
        self._update_image_viewer()

    def closeEvent(self, event):
        if hasattr(self, 'thumbnail_loader') and self.thumbnail_loader is not None:
            self.thumbnail_loader.stop()
            self.thumbnail_loader.wait()
        super().closeEvent(event)
