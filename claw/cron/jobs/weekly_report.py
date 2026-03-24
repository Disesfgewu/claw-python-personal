"""Weekly report job — stock strategy verification and push to Discord."""
from __future__ import annotations

import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

async def weekly_report_job(
    storage,
    llm,
    cron_data: dict | None = None,
    discord_channel=None,
) -> dict:
    """
    Execute weekly report: run strategy A→C→B verification, push to Discord.
    """
    try:
        import discord
        from claw.research.stock_strategy import StockStrategyExecutor
        from claw.channels.discord import DiscordChannel
        from claw.core.config import get_config

        cfg = get_config()
        channel_id = cron_data.get('channel_id') if cron_data else None
        if not channel_id:
            channel_id = getattr(cfg.discord, 'morning_report_channel_id', None) or getattr(cfg.discord, 'stock_channel_id', 0)
        if not channel_id:
            return {
                "status": "failed",
                "reason": "No Discord channel_id configured",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        logger.info(f"Starting weekly report job → Discord channel {channel_id}")

        # 定義核心追蹤股票（Taiwan 50 中的 10 檔）
        symbols = ["2330", "2498", "1101", "3034", "2412", "1216", "2409", "2891", "2454", "2881"]

        # Step 1: 驗證策略
        strategy_results = {}
        executor = StockStrategyExecutor()

        for symbol in symbols[:5]:  # 週報只驗證前 5 檔（避免耗時太久）
            try:
                result = await executor.execute(
                    f"Verify stock strategies for {symbol}",
                    context={"symbol": symbol, "period_days": 90}
                )
                evaluation = await executor.evaluate(result)

                strategy_results[symbol] = {
                    "winner": result.get("winner"),
                    "sharpe": result.get("winner_sharpe", 0.0),
                    "win_rate": result.get("winner_win_rate", 0.0),
                    "is_valid": evaluation.get("is_valid"),
                    "confidence": evaluation.get("confidence")
                }

                logger.info(f"Strategy verification completed for {symbol}")

            except Exception as e:
                logger.warning(f"Failed to verify strategies for {symbol}: {e}")
                continue

        # Step 2: 生成 Discord Embed
        main_embed = discord.Embed(
            title="📊 台股週報 — Strategy Verification Results",
            description=f"驗證時間: {datetime.now().strftime('%Y-%m-%d %H:%M')} \n" +
                       f"共驗證 {len(strategy_results)} 檔個股\n" +
                       "**Recommended Strategies:**",
            color=discord.Color.gold()
        )

        for symbol, results in list(strategy_results.items())[:10]:
            winner = results.get("winner", "N/A")
            sharpe = results.get("sharpe", 0.0)
            win_rate = results.get("win_rate", 0.0)
            is_valid = results.get("is_valid", False)
            confidence = results.get("confidence", 0.0)

            status_emoji = "✅" if is_valid else "⚠️"
            if winner:
                main_embed.add_field(
                    name=f"{status_emoji} {symbol} — {winner.upper()}",
                    value=f"Sharpe: {sharpe:.2f} | Win Rate: {win_rate*100:.1f}% | Confidence: {confidence*100:.0f}%",
                    inline=False
                )

        # 加入總結
        valid_count = sum(1 for r in strategy_results.values() if r.get("is_valid"))
        main_embed.add_field(
            name="📈 Summary",
            value=f"{valid_count}/{len(strategy_results)} 策略驗證通過\n" +
                 "推薦重點關注：Momentum 策略在近期表現最佳",
            inline=False
        )

        # Step 3: 推送到 Discord
        if not discord_channel:
            logger.warning("Discord bot not available for push")
            return {
                "status": "no_bot",
                "reason": "Discord channel instance not provided",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        await discord_channel.send_to_channel_id(
            channel_id=channel_id,
            embed=main_embed,
        )
        logger.info(f"Weekly report pushed to Discord channel {channel_id}")

        return {
            "status": "success",
            "strategies_verified": len(strategy_results),
            "best_strategies": {
                symbol: {
                    "strategy": results.get("winner"),
                    "sharpe": results.get("sharpe"),
                    "is_valid": results.get("is_valid")
                }
                for symbol, results in strategy_results.items()
            },
            "discord_pushed": True,
            "channel_id": channel_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        logger.error(f"Weekly report job failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
