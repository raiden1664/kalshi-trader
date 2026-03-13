SPARK_CHARS = " ▁▂▃▄▅▆▇█"

def sparkline(values: list, color: str = "#00e676", width: int = 44) -> str:
    if not values:
        return "[dim]no data[/dim]"
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    step = max(1, len(values) // width)
    chars = [SPARK_CHARS[int((values[i] - lo) / span * (len(SPARK_CHARS) - 1))]
             for i in range(0, len(values), step)]
    spark = "".join(chars[:width])
    arrow = "▲" if len(values) > 1 and values[-1] >= values[0] else "▼"
    ac    = "#00e676" if arrow == "▲" else "#ff4444"
    return f"[{color}]{spark}[/{color}] [{ac}]{arrow} {values[-1]:.0f}¢[/{ac}]"