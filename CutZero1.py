import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel, 
                           QFileDialog, QProgressBar, QVBoxLayout, QWidget,
                           QSlider, QHBoxLayout, QSpinBox, QDoubleSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips
import numpy as np

class SilenceRemover(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, input_path, threshold=0.04, chunk_duration=0.1):
        super().__init__()
        self.input_path = input_path
        self.threshold = threshold
        self.chunk_duration = chunk_duration
        self.is_audio_only = input_path.lower().endswith(('.mp3', '.wav', '.ogg', '.flac', '.aac'))
        
    def run(self):
        try:
            self.status.emit("Loading media...")
            
            if self.is_audio_only:
                media = AudioFileClip(self.input_path)
                audio = media
            else:
                media = VideoFileClip(self.input_path)
                audio = media.audio
                
            if audio is None:
                raise Exception("No audio track found in the file!")
                
            self.progress.emit(10)
            
            # Analyze audio in chunks
            self.status.emit("Analyzing audio...")
            audio_chunks = []
            duration = media.duration
            
            # Process chunks
            chunk_count = int(duration / self.chunk_duration)
            for i, t in enumerate(np.arange(0, duration, self.chunk_duration)):
                end_t = min(t + self.chunk_duration, duration)
                if self.is_audio_only:
                    chunk = audio.subclip(t, end_t)
                else:
                    chunk = media.subclip(t, end_t).audio
                    
                if chunk is not None:
                    audio_chunks.append((t, np.sqrt(np.mean(chunk.to_soundarray()**2))))
                progress = 10 + int((i / chunk_count) * 30)
                self.progress.emit(progress)
            
            self.status.emit("Detecting silent parts...")
            nonsilent_chunks = []
            
            for t, volume in audio_chunks:
                if volume > self.threshold:
                    nonsilent_chunks.append(t)
            
            self.progress.emit(50)
            self.status.emit("Creating clips...")
            
            if not nonsilent_chunks:
                raise Exception("No non-silent parts found in the media!")
            
            clips = []
            start_time = nonsilent_chunks[0]
            prev_time = start_time
            
            for t in nonsilent_chunks[1:]:
                if t - prev_time > self.chunk_duration * 1.5:
                    clips.append(media.subclip(
                        max(0, start_time - self.chunk_duration),
                        min(duration, prev_time + self.chunk_duration)
                    ))
                    start_time = t
                prev_time = t
            
            # Add the last clip
            clips.append(media.subclip(
                max(0, start_time - self.chunk_duration),
                min(duration, prev_time + self.chunk_duration)
            ))
            
            self.progress.emit(70)
            self.status.emit("Combining clips...")
            
            if clips:
                output_path = os.path.splitext(self.input_path)[0] + "_no_silence"
                
                if self.is_audio_only:
                    final_media = concatenate_audioclips(clips)
                    # Add the appropriate extension based on input
                    ext = os.path.splitext(self.input_path)[1]
                    output_path += ext
                    
                    self.status.emit("Saving audio...")
                    final_media.write_audiofile(
                        output_path,
                        logger=None
                    )
                else:
                    final_media = concatenate_videoclips(clips)
                    output_path += ".mp4"
                    
                    self.status.emit("Saving video...")
                    final_media.write_videofile(
                        output_path,
                        codec='libx264',
                        audio_codec='aac',
                        temp_audiofile="temp-audio.m4a",
                        remove_temp=True,
                        logger=None
                    )
                
                final_media.close()
            
            media.close()
            self.progress.emit(100)
            self.finished.emit(output_path)
            
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Media Silence Remover")
        self.setFixedSize(500, 300)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create UI elements
        self.select_button = QPushButton("Select Video or Audio")
        self.select_button.setFixedHeight(40)
        
        # Threshold control with updated range for lower threshold limit
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("Silence Threshold:")
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setRange(1, 200)  # Range from 1 to 200
        self.threshold_slider.setValue(40)  # Set default value to 40
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(20)
        self.threshold_label_value = QLabel(f"Threshold: {0.0001 + self.threshold_slider.value() / 10000:.4f}")
        
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_slider)
        threshold_layout.addWidget(self.threshold_label_value)
        
        # Status and progress
        self.status_label = QLabel("Select a video or audio file to begin")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        
        # Add elements to layout
        layout.addWidget(self.select_button)
        layout.addLayout(threshold_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        
        # Add stretches for better layout
        layout.addStretch()
        
        # Connect signals
        self.select_button.clicked.connect(self.select_media)
    
    def update_threshold_label(self):
        # Updated calculation to reach 0.0002 at the lowest point
        value = 0.0001 + self.threshold_slider.value() / 10000
        self.threshold_label_value.setText(f"Threshold: {value:.4f}")
    
    def select_media(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video or Audio",
            "",
            "Media Files (*.mp4 *.avi *.mkv *.mov *.mp3 *.wav *.ogg *.flac *.aac)"
        )
        
        if file_path:
            self.status_label.setText("Processing media...")
            self.select_button.setEnabled(False)
            self.progress_bar.show()
            self.progress_bar.setValue(0)
            
            # Start processing in background with updated threshold calculation
            self.worker = SilenceRemover(
                file_path,
                threshold=0.0001 + self.threshold_slider.value() / 10000  # Updated conversion for lower threshold
            )
            self.worker.progress.connect(self.update_progress)
            self.worker.status.connect(self.update_status)
            self.worker.finished.connect(self.processing_finished)
            self.worker.error.connect(self.processing_error)
            self.worker.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, message):
        self.status_label.setText(message)
    
    def processing_finished(self, output_path):
        self.status_label.setText(f"Done! Saved as:\n{output_path}")
        self.select_button.setEnabled(True)
        
    def processing_error(self, error_message):
        self.status_label.setText(f"Error: {error_message}")
        self.select_button.setEnabled(True)
        self.progress_bar.hide()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()