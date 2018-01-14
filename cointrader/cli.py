# -*- coding: utf-8 -*-
# Импорт библиотек
import click
import sys
import logging
import datetime
from cointrader import db, STRATEGIES
from cointrader.config import Config, get_path_to_config
from cointrader.exchange import Poloniex, BacktestMarket, Market
from cointrader.exchanges.poloniex import ApiError
from cointrader.bot import init_db, get_bot
from cointrader.helpers import render_bot_statistic, render_bot_tradelog

# Создание лога
logging.basicConfig(format = u'%(levelname)-8s [%(asctime)s] %(message)s', level = logging.DEBUG, filename = u'cointrader.log')
log = logging.getLogger(__name__)



class Context(object):

    """Docstring for Context. """

    def __init__(self):
        self.exchange = None

# Создание пустого декоратора
pass_context = click.make_pass_decorator(Context, ensure=True)

# Создание группы команд
@click.group()
# Задаем параметры
@click.option("--config", help="Configuration File for cointrader.", type=click.File("r"))
@pass_context
def main(ctx, config):
    """Console script for cointrader on the Poloniex exchange"""
    init_db()
    if config:
        config = Config(config)
    else:
        config = Config(open(get_path_to_config(), "r"))
    try:
        ctx.exchange = Poloniex(config)
    except ApiError as ex:
        click.echo(ex.message)
        sys.exit(1)


# Добавляем команды
@click.command()
@click.option("--order-by-volume", help="Order markets by their trading volume", is_flag=True)
@click.option("--order-by-profit", help="Order markets by their current profit", is_flag=True)
@click.option("--limit", help="Limit output to NUM markets", default=10)
@pass_context
def explore(ctx, order_by_volume, order_by_profit, limit):
    """List top markets. On default list markets which are profitable and has a high volume."""
    markets = ctx.exchange.markets
    if not order_by_volume and not order_by_profit:
        markets = ctx.exchange.get_top_markets(markets, limit)
        for market in markets:
            url = "https://poloniex.com/exchange#{}".format(market[0].lower())
            click.echo("{:<10} {:>6}% {:>10} {:>20}".format(market[0], market[1]["change"], market[1]["volume"], url))
        if len(markets) == 0:
            click.echo("Sorry. Can not find any market which is in the TOP{} for profit and trade volume. Try to increase the limit using the --limit parameter.".format(limit))
    elif order_by_volume:
        markets = ctx.exchange.get_top_volume_markets(markets, limit)
        for market in markets:
            url = "https://poloniex.com/exchange#{}".format(market[0].lower())
            click.echo("{:<10} {:>10} {:>6}% {:>20}".format(market[0], market[1]["volume"], market[1]["change"], url))
        if len(markets) == 0:
            click.echo("Sorry. Can not find any market which is in the TOP{} for trade volume. Try to increase the limit using the --limit parameter.".format(limit))
    elif order_by_profit:
        markets = ctx.exchange.get_top_profit_markets(markets, limit)
        for market in markets:
            url = "https://poloniex.com/exchange#{}".format(market[0].lower())
            click.echo("{:<10} {:>6}% {:>10} {:>20}".format(market[0], market[1]["change"], market[1]["volume"], url))
        if len(markets) == 0:
            click.echo("Sorry. Can not find any market which is in the TOP{} for profit. Try to increase the limit using the --limit parameter.".format(limit))


@click.command()
@pass_context
def balance(ctx):
    """Overview of your balances on the market."""
    click.echo("{:<4}  {:>12} {:>12}".format("CUR", "total", "btc_value"))
    click.echo("{}".format("-" * 31))
    coins = ctx.exchange.coins
    for currency in coins:
        click.echo("{:<4}: {:>12} {:>12}".format(currency, coins[currency].quantity, coins[currency].value))
    click.echo("{}".format("-" * 31))
    click.echo("{:<9}: {:>20}".format("TOTAL BTC", ctx.exchange.total_btc_value))
    click.echo("{:<9}: {:>20}".format("TOTAL USD", ctx.exchange.total_euro_value))

# Добавляем команды
@click.command()
@click.argument("market")
@click.option("--resolution", help="Resolution of the chart which is used for trend analysis", default="30m")
@click.option("--start", help="Datetime to begin trading", default=None)
@click.option("--end", help="Datetime to end trading", default=None)
@click.option("--lastndays", help="backtest in the last N days", default=int)
@click.option("--automatic", help="Start cointrader in automatic mode.", is_flag=True)
@click.option("--papertrade", help="Just simulate the strategy on the chart.", is_flag=True)
@click.option("--backtest", help="Just backtest the strategy on the chart.", is_flag=True)
@click.option("--strategy", help="Stratgegy used for trading.", default="trend", type=click.Choice(STRATEGIES.keys()))
@click.option("--btc", help="Set initial amount of BTC the bot will use for trading.", type=float)
@click.option("--coins", help="Set initial amount of coint the bot will use for trading.", type=float)
@click.option("--verbose", help="Вывод на экран логируемых сообщений.", is_flag=False)
@click.option("--percent", help="Процент торговли от всей суммы.", is_flag=False)
@pass_context
def start(ctx, market, resolution, start, end, automatic, backtest, papertrade, strategy, btc, coins, verbose, percent, lastndays):
    """Start a new bot on the given market and the given amount of BTC"""
    # Check start and end date
    try:
        if start:
            start = datetime.datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        if end:
            end = datetime.datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        click.echo("Date is not valid. Must be in format 'YYYY-mm-dd HH:MM:SS'")
        sys.exit(1)

    if lastndays:

        try:
            now_time = datetime.datetime.now()
            delta = datetime.timedelta(days=int(lastndays))
            date_N_days_ago = now_time - delta

            start = date_N_days_ago
            end = now_time
        except ValueError:
            click.echo("Days is not valid. Must be in 1 2 34 ...'")
            sys.exit(1)

    # Build the market on which the bot will operate
    # First check if the given market is a valid market. If not exit
    # here with a error message.
    # If the market is valid create a real market instance of and
    # instance for backtests depending on the user input.
    if ctx.exchange.is_valid_market(market):
        if backtest:
            if start is None or end is None:
                click.echo("Error! For backtests you must provide a timeframe by setting start and end!")
                sys.exit(1)
            market = BacktestMarket(ctx.exchange, market)
        else:
            market = Market(ctx.exchange, market)
    else:

        click.echo("Market {} is not available".format(market))
        sys.exit(1)

    # Check if the given resolution is supported
    if not ctx.exchange.is_valid_resolution(resolution):
        valid_resolutions = ", ".join(ctx.exchange.resolutions.keys())
        click.echo("Resolution {} is not supported.\n"
                   "Please choose one of the following: {}".format(resolution,
                                                                   valid_resolutions))
        sys.exit(1)

    # Initialise a strategy.
    strategy = STRATEGIES[strategy]()

    # Устанановлен фиксированный количество монет
    if coins:
        fixcoin = True
    else:
        fixcoin = False

    bot = get_bot(market, strategy, resolution, start, end, btc, coins, fixcoin, verbose, percent, automatic)
    bot.start(backtest, automatic)

    if backtest:
        click.echo(render_bot_tradelog(bot.trades))
        click.echo(render_bot_statistic(bot.stat(backtest)))
        db.delete(bot)
        db.commit()


@click.command()
@click.argument("dollar", type=float)
@pass_context
def exchange(ctx, dollar):
    """Will return how many BTC you get for the given amount of dollar"""
    btc = ctx.exchange.dollar2btc(dollar)
    click.echo("{}$ ~ {}BTC".format(dollar, btc))


main.add_command(explore)
main.add_command(balance)
main.add_command(exchange)
main.add_command(start)

# Запуск сценария
if __name__ == "__main__":
    main()
