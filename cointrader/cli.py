# -*- coding: utf-8 -*-
# Импорт библиотек
import click
import sys
import logging
import datetime
import sys
import os.path
import pandas as pd
from terminaltables import AsciiTable

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from cointrader import db, STRATEGIES
from cointrader.config import Config, get_path_to_config
from cointrader.exchange import Poloniex, BacktestMarket, Market
from cointrader.exchanges.poloniex import ApiError
from cointrader.bot import init_db, get_bot, create_bot
from cointrader.helpers import render_bot_statistic, render_bot_tradelog

# Создание лога
logging.basicConfig(format=u'%(levelname)-8s [%(asctime)s] %(message)s', level=logging.DEBUG,
                    filename=u'cointrader.log')
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
    """Console script for cointrader on the Poloniex exchange
    :param ctx:
    :param config:
    """
    init_db()
    if config:
        config = Config(config)
    else:
        config = Config(open(get_path_to_config(), "r"))
    try:
        ctx.exchange = Poloniex(config)
    except Exception as ex:
        click.echo(ex)
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
            click.echo(
                "Sorry. Can not find any market which is in the TOP{} for profit and trade volume. Try to increase the limit using the --limit parameter.".format(
                    limit))
    elif order_by_volume:
        markets = ctx.exchange.get_top_volume_markets(markets, limit)
        for market in markets:
            url = "https://poloniex.com/exchange#{}".format(market[0].lower())
            click.echo("{:<10} {:>10} {:>6}% {:>20}".format(market[0], market[1]["volume"], market[1]["change"], url))
        if len(markets) == 0:
            click.echo(
                "Sorry. Can not find any market which is in the TOP{} for trade volume. Try to increase the limit using the --limit parameter.".format(
                    limit))
    elif order_by_profit:
        markets = ctx.exchange.get_top_profit_markets(markets, limit)
        for market in markets:
            url = "https://poloniex.com/exchange#{}".format(market[0].lower())
            click.echo("{:<10} {:>6}% {:>10} {:>20}".format(market[0], market[1]["change"], market[1]["volume"], url))
        if len(markets) == 0:
            click.echo(
                "Sorry. Can not find any market which is in the TOP{} for profit. Try to increase the limit using the --limit parameter.".format(
                    limit))


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
@click.option("--btc", help="Set initial amountof BTC the bot will use for trading.", type=float)
@click.option("--coins", help="Set initial amount of coint the bot will use for trading.", type=float)
@click.option("--verbose", help="Вывод на экран логируемых сообщений.", is_flag=False)
@click.option("--percent", help="Процент торговли от всей суммы.", is_flag=False)
@pass_context
def start(ctx, market, resolution, start, end, automatic, backtest, papertrade, strategy, btc, coins, verbose, percent,
          lastndays, other_time=False):
    """Start a new bot on the given market and the given _amount_deleted of BTC
    :param ctx:
    :param market:
    :param resolution:
    :param start:
    :param end:
    :param automatic:
    :param backtest:
    :param papertrade:
    :param strategy:
    :param btc:
    :param coins:
    :param verbose:
    :param percent:
    :param lastndays:
    """
    # Check start and end date
    try:
        if start:
            start = datetime.datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
        elif end:
            end = datetime.datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        click.echo("Date is not valid. Must be in format 'YYYY-mm-dd HH:MM:SS'")
        sys.exit(1)

    end, start = set_start_end(end, lastndays, start)

    # Build the market on which the bot will operate
    # First check if the given market is a valid market. If not exit
    # here with a error message.
    # If the market is valid create a real market instance of and
    # instance for backtests depending on the user input.
    market = set_market(backtest, ctx, end, market, start)

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

    bot = get_bot(market, strategy, resolution, start, end, btc, coins, fixcoin, verbose, percent, automatic=True,
                  memory_only=False)

    if other_time:
        bot.start(backtest, automatic)
        pass

    df = pd.DataFrame.from_dict(bot._market._exchange.markets, orient='index')
    df['change'] = df.change.astype(float)
    df['volume'] = df.volume.astype(float)
    df = df.sort_values(by=['volume', 'change'], ascending=False)
    df_filtered = df[(df['volume'] > 5) & (df['change'] > 0)]
    df_filtered = df_filtered.sort_values(by=['change'], ascending=False)

    test_markets = []
    out = [["ПАРА", "ОБЪЕМ", "ИЗМЕНЕНИЯ"]]
    for current_market, row in df_filtered.iterrows():
        volume, change = (row['volume'], row['change'])
        values = []
        values.append(current_market)
        values.append(volume)
        values.append(str(change) + "%")
        out.append(values)
        end, start = set_start_end(end, 1, start)

        if current_market != market._name:
            test_markets.append(set_market(True, ctx, end, current_market, start))

    table = AsciiTable(out).table

    print("\n".join(["\nРастущий тренд:", table]))

    start_before = start
    end_before = end
    amount_before = bot._amount_deleted
    end, start = set_start_end(end, 1, start)

    db.delete(bot)
    db.commit()

    best_testing_market = []
    test_markets.append(set_market(backtest, ctx, end, market._name, start))
    for current_market in test_markets:
        bot = create_bot(current_market, strategy, resolution, start, end, btc, coins, fixcoin, verbose, percent,
                         automatic=True)
        for trade in bot.trades:
            try:
                if trade != bot.trades[0]:
                    db.delete(trade)
            except:
                pass
        bot.start(backtest=True, automatic=True)
        try:
            db.delete(bot)
            db.commit()

        except:
            pass
        best_testing_market.append({"market": current_market._name, "profit": bot.profit})

    bot = get_bot(market, strategy, resolution, start, end, btc, coins, fixcoin, verbose, percent, automatic,
                  memory_only=False)
    bot._start = start_before
    bot._end = end_before
    bot._amount_deleted = amount_before

    if best_testing_market[-1]["profit"] > 0:
        print("Текущий заработок на паре {} составляет {}".format(best_testing_market[-1]["profit"],
                                                                  best_testing_market[-1]["market"]))
        bot.start(backtest=False, automatic=automatic)
    else:
        print("На данной паре заработок отсутсвует.")

    best_pair = None
    out = [["ПАРА", "ЗАРАБОТОК"]]
    for item in best_testing_market:
        if item["profit"] > 0:
            if best_pair == None:
                best_pair = item
            elif item["profit"] > best_pair["profit"]:
                best_pair = item
            values = []
            values.append(item["market"])
            values.append(item["profit"])
            out.append(values)

    table = AsciiTable(out).table
    print("\n".join(["\nПрибыльные пары:", table]))

    if best_pair != None:
        print("\nВыбрана пара: %s, заработок: %f" % (best_pair["market"], best_pair["profit"]))

        # market = set_market(backtest, ctx, end, best_pair['market'], start)
        # bot = get_bot(market, strategy, resolution, start, end, _btc_deleted, coins, fixcoin, verbose, _percent_deleted, automatic, memory_only=False)
        # bot._start = start_before
        # bot._end = end_before
        # bot._amount_deleted = amount_before
        # bot._btc_deleted = btc_before
        # bot.start(False, automatic)

    if backtest:
        click.echo(render_bot_tradelog(bot.trades))
        click.echo(render_bot_statistic(bot, bot.stat(True)))
        db.delete(bot)
        db.commit()


def set_market(backtest, ctx, end, market, start):
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
    return market


def set_start_end(end, lastndays, start):
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
    return end, start


@click.command()
@click.argument("dollar", type=float)
@pass_context
def exchange(ctx, dollar):
    """Will return how many BTC you get for the given _amount_deleted of dollar"""
    btc = ctx.exchange.dollar2btc(dollar)
    click.echo("{}$ ~ {}BTC".format(dollar, btc))


main.add_command(explore)
main.add_command(balance)
main.add_command(exchange)
main.add_command(start)

# Запуск сценария
if __name__ == "__main__":
    main()
