"""Universal chart generation for any data type (weather, reports, timeseries, etc)."""
from __future__ import annotations

import json
import logging
from typing import Optional, Any
from io import BytesIO

logger = logging.getLogger(__name__)

# 設定 matplotlib 中文字體
import matplotlib
try:
    import matplotlib.font_manager as fm
    _cjk_fonts = [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for _font_path in _cjk_fonts:
        import os
        if os.path.exists(_font_path):
            fm.fontManager.addfont(_font_path)
            _prop = fm.FontProperties(fname=_font_path)
            matplotlib.rcParams['font.family'] = _prop.get_name()
            break
except Exception:  # nosec B110
    pass


def generate_timeseries_chart(
    title: str,
    data_points: list[dict],
    x_key: str = "date",
    y_key: str = "value",
    y_label: str = "Value",
) -> bytes:
    """
    生成時間序列折線圖（適用於天氣、股價趨勢等）。

    Args:
        title: 圖表標題
        data_points: 數據點列表，每個包含 x_key 和 y_key
        x_key: X軸鍵（如 "date"、"time"）
        y_key: Y軸鍵（如 "temperature"、"value"）
        y_label: Y軸標籤

    Returns:
        PNG bytes

    Example:
        >>> data = [
        ...     {"date": "2026-03-20", "temp": 15},
        ...     {"date": "2026-03-21", "temp": 18},
        ...     {"date": "2026-03-22", "temp": 22},
        ... ]
        >>> chart_bytes = generate_timeseries_chart(
        ...     "台北溫度", data, x_key="date", y_key="temp", y_label="溫度(°C)"
        ... )
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime
        from typing import cast

        # 準備數據
        x_vals = []
        y_vals = []

        for point in data_points:
            x_val = point.get(x_key)
            y_val = point.get(y_key)

            if x_val is None or y_val is None:
                continue

            # 嘗試解析日期
            if isinstance(x_val, str):
                try:
                    x_val = datetime.fromisoformat(x_val)
                except (ValueError, TypeError):
                    x_val = str(x_val)  # 保持為字符串

            x_vals.append(x_val)
            y_vals.append(float(y_val) if isinstance(y_val, (int, float)) else 0)

        if not x_vals or not y_vals:
            logger.warning(f"No valid data for chart: {title}")
            return b""

        # 創建圖表
        fig, _ax = plt.subplots(figsize=(12, 6))
        ax = cast(Any, _ax)
        ax.plot(x_vals, y_vals, marker='o', linewidth=2, markersize=6, color='#1f77b4')
        ax.fill_between(range(len(y_vals)), y_vals, alpha=0.3, color='#1f77b4')

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_ylabel(y_label, fontsize=12)
        ax.grid(True, alpha=0.3)

        # 格式化 X 軸
        if any(isinstance(x, datetime) for x in x_vals):
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            fig.autofmt_xdate(rotation=45, ha='right')

        # 保存為 PNG
        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)

        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Failed to generate timeseries chart: {e}")
        return b""


def generate_bar_chart(
    title: str,
    categories: list[str],
    values: list[float],
    y_label: str = "Value",
) -> bytes:
    """
    生成柱狀圖（適用於指標比較、排名等）。

    Args:
        title: 圖表標題
        categories: 類別名稱列表
        values: 對應的數值列表
        y_label: Y軸標籤

    Returns:
        PNG bytes

    Example:
        >>> chart_bytes = generate_bar_chart(
        ...     "各產業表現",
        ...     ["半導體", "金融", "電子"],
        ...     [15.2, 8.5, 12.1],
        ...     y_label="漲幅(%)"
        ... )
    """
    try:
        import matplotlib.pyplot as plt
        from typing import cast

        fig, _ax = plt.subplots(figsize=(12, 6))
        ax = cast(Any, _ax)

        colors = ['#1f77b4' if v >= 0 else '#d62728' for v in values]
        ax.bar(categories, values, color=colors, alpha=0.7)

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_ylabel(y_label, fontsize=12)
        ax.grid(True, alpha=0.3, axis='y')

        # 在柱上顯示數值
        for i, v in enumerate(values):
            ax.text(i, v, f'{v:.1f}', ha='center', va='bottom' if v >= 0 else 'top')

        fig.autofmt_xdate(rotation=45, ha='right')

        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)

        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Failed to generate bar chart: {e}")
        return b""


def generate_heatmap_chart(
    title: str,
    data_matrix: list[list[float]],
    x_labels: list[str],
    y_labels: list[str],
) -> bytes:
    """
    生成熱力圖（適用於相關性、強度分佈等）。

    Args:
        title: 圖表標題
        data_matrix: 二維數據矩陣
        x_labels: X軸標籤
        y_labels: Y軸標籤

    Returns:
        PNG bytes
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from typing import cast

        fig, _ax = plt.subplots(figsize=(12, 6))
        ax = cast(Any, _ax)

        im = ax.imshow(data_matrix, cmap='RdYlGn', aspect='auto')

        ax.set_xticks(range(len(x_labels)))
        ax.set_yticks(range(len(y_labels)))
        ax.set_xticklabels(x_labels, rotation=45, ha='right')
        ax.set_yticklabels(y_labels)

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)

        # 添加顏色條
        cbar = plt.colorbar(im, ax=ax)

        fig.tight_layout()

        buffer = BytesIO()
        fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)
        plt.close(fig)

        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Failed to generate heatmap chart: {e}")
        return b""


def detect_and_generate_chart(
    query: str,
    data: Any,
    response: str,
) -> Optional[bytes]:
    """
    根據查詢類型自動偵測並生成適當的圖表。

    Args:
        query: 用戶查詢
        data: 查詢結果數據
        response: LLM 回應

    Returns:
        PNG bytes 或 None

    支持的類型：
    - 股票：K 線圖（已由 stock_handler 處理）
    - 天氣：溫度/濕度曲線圖
    - 趨勢：時間序列圖
    - 比較：柱狀圖
    """
    try:
        # 檢測天氣查詢
        if any(keyword in query.lower() for keyword in ['天氣', 'weather', '溫度', '降雨', '濕度']):
            logger.info("Detected weather query, attempting to generate temperature chart")

            # 嘗試從數據或回應中提取溫度數據
            if isinstance(data, dict):
                temps = data.get('temperatures') or data.get('temps') or data.get('data')
                if isinstance(temps, list):
                    data_points = [
                        {"date": f"Day {i+1}", "temp": t}
                        for i, t in enumerate(temps)
                    ]
                    return generate_timeseries_chart(
                        "溫度趨勢",
                        data_points,
                        x_key="date",
                        y_key="temp",
                        y_label="溫度(°C)"
                    )

        # 檢測趨勢/時間序列查詢
        if any(keyword in query.lower() for keyword in ['趨勢', 'trend', '變化', '增長', '下降']):
            logger.info("Detected trend query")

            if isinstance(data, dict) and 'data' in data:
                data_list = data.get('data', [])
                if isinstance(data_list, list) and len(data_list) > 0:
                    return generate_timeseries_chart(
                        "趨勢圖",
                        data_list,
                        y_label="數值"
                    )

        # 檢測比較/排名查詢
        if any(keyword in query.lower() for keyword in ['比較', 'comparison', '排名', '排序', '前']):
            logger.info("Detected comparison query")

            if isinstance(data, dict) and 'items' in data:
                items = data.get('items', [])
                if isinstance(items, list) and len(items) > 0:
                    categories = [item.get('name', f'Item {i}') for i, item in enumerate(items)]
                    values = [float(item.get('value', 0)) for item in items]
                    return generate_bar_chart(
                        "比較圖",
                        categories,
                        values
                    )

        logger.info("No matching chart type detected")
        return None

    except Exception as e:
        logger.error(f"Chart detection and generation failed: {e}")
        return None
