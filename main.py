import sys
from ui.window import PinterestDownloaderWindow
from PySide6.QtWidgets import QApplication

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # If any CLI argument is provided, run CLI mode
        import download_images

        download_images.main()
    else:
        # No CLI argument, run the UI
        app = QApplication(sys.argv)
        window = PinterestDownloaderWindow()
        window.show()
        sys.exit(app.exec())
