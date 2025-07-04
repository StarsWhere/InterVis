
from PyQt6.QtGui import QIcon
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
时间序列图表对话框
"""
import logging
import numpy as np
import os 
from datetime import datetime
from typing import Tuple, Optional
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QWidget, QMessageBox, QFileDialog
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

class TimeSeriesDialog(QDialog):
    """一个显示时间序列及其FFT的对话框。"""
    
    def __init__(self, point_coords: Tuple[float, float], data_manager, filter_clause: str, output_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowIcon(QIcon("png/icon.png")) 
        self.dm = data_manager
        self.point_coords = point_coords
        self.filter_clause = filter_clause
        self.output_dir = output_dir
        self.current_df = None
        
        self.setWindowTitle(f"时间序列分析 @ (X: {point_coords[0]:.2e}, Y: {point_coords[1]:.2e})")
        self.setMinimumSize(800, 700)

        main_layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("选择变量:"))
        self.variable_combo = QComboBox()
        plot_vars = [v for v in self.dm.get_variables() if v != 'source_file']
        self.variable_combo.addItems(plot_vars)
        self.variable_combo.currentIndexChanged.connect(self.plot_data)
        controls_layout.addWidget(self.variable_combo)
        controls_layout.addStretch()
        self.fft_button = QPushButton("计算 FFT")
        self.fft_button.clicked.connect(self.plot_fft)
        self.fft_button.setEnabled(False)
        controls_layout.addWidget(self.fft_button)

        self.export_fft_button = QPushButton("导出 FFT(CSV)")
        self.export_fft_button.clicked.connect(self.export_fft_results_csv)
        self.export_fft_button.setEnabled(False)
        controls_layout.addWidget(self.export_fft_button)

        self.export_image_button = QPushButton("导出图片(PNG)")
        self.export_image_button.clicked.connect(self.export_image)
        controls_layout.addWidget(self.export_image_button)
        main_layout.addLayout(controls_layout)

        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax_time = self.figure.add_subplot(2, 1, 1)
        self.ax_fft = self.figure.add_subplot(2, 1, 2)
        main_layout.addWidget(self.canvas)
        
        self.figure.tight_layout(pad=3.0)
        self.plot_data()

    def plot_data(self):
        selected_variable = self.variable_combo.currentText()
        if not selected_variable: return

        self.ax_time.clear(); self.ax_fft.clear()
        self.ax_fft.set_yticklabels([]); self.ax_fft.set_xticklabels([])
        self.ax_fft.set_title("快速傅里叶变换 (FFT)")
        self.ax_fft.set_xlabel("频率 (Hz)")
        self.ax_fft.set_ylabel("振幅")
        
        try:
            x_range = self.dm.global_stats.get('x_global_max', 1) - self.dm.global_stats.get('x_global_min', 0)
            y_range = self.dm.global_stats.get('y_global_max', 1) - self.dm.global_stats.get('y_global_min', 0)
            tolerance = max(x_range * 0.01, y_range * 0.01, 1e-6)

            self.current_df = self.dm.get_timeseries_at_point(selected_variable, self.point_coords, tolerance)

            if self.current_df is None or self.current_df.empty:
                self.ax_time.text(0.5, 0.5, "在此位置找不到时间序列数据", ha='center', va='center', transform=self.ax_time.transAxes)
                self.fft_button.setEnabled(False)
                self.export_fft_button.setEnabled(False)
            else:
                time_col_name = self.dm.time_variable
                self.ax_time.plot(self.current_df[time_col_name], self.current_df[selected_variable], marker='.', linestyle='-')
                self.ax_time.set_title(f"'{selected_variable}' 的时间演化")
                self.ax_time.set_xlabel(f"时间 ({time_col_name})")
                self.ax_time.set_ylabel(f"值 ({selected_variable})")
                self.ax_time.grid(True, linestyle='--', alpha=0.6)
                
                formatter = ticker.ScalarFormatter(useMathText=True); formatter.set_scientific(True); formatter.set_powerlimits((-3, 3))
                self.ax_time.yaxis.set_major_formatter(formatter)
                
                is_valid_for_fft = len(self.current_df) > 1 and np.all(np.diff(self.current_df[time_col_name]) > 0)
                self.fft_button.setEnabled(is_valid_for_fft)
                self.export_fft_button.setEnabled(False) 

        except Exception as e:
            logger.error(f"绘制时间序列图失败: {e}", exc_info=True)
            self.ax_time.text(0.5, 0.5, f"绘图失败:\n{e}", ha='center', va='center', color='red')
            self.fft_button.setEnabled(False)
            self.export_fft_button.setEnabled(False)
            
        self.canvas.draw()

    def plot_fft(self):
        if self.current_df is None or self.current_df.empty: return
        
        selected_variable = self.variable_combo.currentText()
        time_col_name = self.dm.time_variable
        signal = self.current_df[selected_variable].values
        timestamps = self.current_df[time_col_name].values
        
        N = len(signal)
        if N < 2: return
        
        time_diffs = np.diff(timestamps)
        if np.any(time_diffs <= 0):
            self.ax_fft.clear()
            self.ax_fft.text(0.5, 0.5, "时间戳不均匀或无效，无法计算FFT", ha='center', color='red')
            self.canvas.draw()
            self.export_fft_button.setEnabled(False)
            return
            
        T = np.mean(time_diffs)
        if T == 0:
            self.ax_fft.clear(); self.ax_fft.text(0.5, 0.5, "时间步长为零，无法计算FFT", ha='center', color='red'); self.canvas.draw(); return

        self.yf = np.fft.fft(signal - np.mean(signal))
        self.xf = np.fft.fftfreq(N, T)[:N//2]
        
        self.ax_fft.clear()
        self.ax_fft.plot(self.xf, 2.0/N * np.abs(self.yf[0:N//2]))
        self.ax_fft.set_title(f"'{selected_variable}' 的快速傅里叶变换 (FFT)")
        self.ax_fft.set_xlabel("频率 (Hz)")
        self.ax_fft.set_ylabel("振幅")
        self.ax_fft.grid(True, linestyle='--', alpha=0.6)
        self.canvas.draw()
        self.export_fft_button.setEnabled(True)

    def _get_common_filename_part(self):
        """生成用于导出的文件名公共部分。"""
        selected_variable = self.variable_combo.currentText()
        x_coord, y_coord = self.point_coords
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"timeseries_x{x_coord:.2e}_y{y_coord:.2e}_{selected_variable}_{timestamp}"

    def export_fft_results_csv(self):
        if not hasattr(self, 'xf') or not hasattr(self, 'yf') or self.xf is None or self.yf is None:
            QMessageBox.warning(self, "无数据", "没有可导出的 FFT 结果。请先计算 FFT。")
            return

        import pandas as pd
        
        os.makedirs(self.output_dir, exist_ok=True)
        filename = f"fft_{self._get_common_filename_part()}.csv"
        file_path = os.path.join(self.output_dir, filename)

        try:
            N = len(self.yf)
            amplitudes = 2.0/N * np.abs(self.yf[0:N//2])
            
            df_fft = pd.DataFrame({
                'Frequency (Hz)': self.xf,
                'Amplitude': amplitudes
            })
            df_fft.to_csv(file_path, index=False)
            logger.info(f"FFT 结果已成功导出到 {file_path}")
            QMessageBox.information(self, "成功", f"FFT 结果已成功导出到:\n{file_path}")
        except Exception as e:
            logger.error(f"导出 FFT 结果失败: {e}", exc_info=True)
            QMessageBox.critical(self, "导出失败", f"导出 FFT 结果失败:\n{e}")

    def export_image(self):
        """直接将当前图表导出为图片。"""
        os.makedirs(self.output_dir, exist_ok=True)
        filename = f"{self._get_common_filename_part()}.png"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            self.figure.savefig(filepath, dpi=300, bbox_inches='tight')
            QMessageBox.information(self, "成功", f"图表已成功导出到:\n{filepath}")
        except Exception as e:
            logger.error(f"导出图表图片失败: {e}", exc_info=True)
            QMessageBox.critical(self, "导出失败", f"导出图片失败:\n{e}")