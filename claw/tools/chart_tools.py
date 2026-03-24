def generate_candlestick_chart(
    symbol: str,
    ohlcv_list: list,
    output_path: str | None = None
) -> bytes:
    """
    Generate candlestick chart as PNG bytes.

    Args:
        symbol: Stock code (e.g., "2330")
        ohlcv_list: List of OHLCV dicts with keys:
            - 'date' (str, YYYY-MM-DD format)
            - 'open', 'high', 'low', 'close' (float)
            - 'volume' (int)
        output_path: If provided, save PNG to this path

    Returns:
        PNG binary data as bytes

    圖表特性：
    - K 線（綠色上升，紅色下降）
    - 20-day + 50-day 移動平均線
    - 成交量柱狀圖（下方）
    - 標題："{symbol} Candlestick Chart"
    - 自動 locale 設定為繁體中文
    """
    import pandas as pd
    import mplfinance as mpf
    from io import BytesIO
    from typing import Any, cast

    # 轉換成 pandas DataFrame（日期為 index）
    df = pd.DataFrame(ohlcv_list)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df = df[['open', 'high', 'low', 'close', 'volume']]

    # 計算移動平均線
    close_s = cast(Any, df['close'])
    df['sma20'] = close_s.rolling(20).mean()
    df['sma50'] = close_s.rolling(50).mean()

    # 組建 mplfinance 樣式
    apds = []
    sma20_s = cast(Any, df['sma20'])
    sma50_s = cast(Any, df['sma50'])
    if sma20_s.notna().sum() > 0:
        apds.append(mpf.make_addplot(sma20_s.values, color='orange', width=1.5))
    if sma50_s.notna().sum() > 0:
        apds.append(mpf.make_addplot(sma50_s.values, color='purple', width=1.5))

    # 生成圖表到 BytesIO
    buffer = BytesIO()
    
    plot_kwargs: dict[str, Any] = dict(
        type='candle',
        style='charles',
        title=f'{symbol} Candlestick Chart',
        ylabel='Price (TWD)',
        volume=True,
        savefig=dict(fname=buffer, dpi=100, bbox_inches='tight')
    )
    if apds:
        plot_kwargs['addplot'] = apds
        
    mpf.plot(df, **plot_kwargs)
    buffer.seek(0)
    png_bytes = buffer.getvalue()

    # 如果指定 output_path，也存一份到檔案
    if output_path:
        with open(output_path, 'wb') as f:
            f.write(png_bytes)

    return png_bytes
