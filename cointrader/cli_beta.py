# -*- coding: utf-8 -*-
# Импорт библиотек
import logging
import os.path
import sys
import time
import click
import pandas as pd
from datetime import datetime, timedelta
from terminaltables import AsciiTable

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from cointrader import db, STRATEGIES
from cointrader.config import Config, get_path_to_config
from cointrader.exchange import Poloniex, Market
from cointrader.bot import init_db, get_bot, create_bot, Active

# Создание лога
logging.basicConfig(format=u'%(levelname)-8s [%(asctime)s] %(message)s', level=logging.DEBUG,
                    filename=u'cointrader.log')
log = logging.getLogger(__name__)


class Context(object):
    """Docstring for Context. """

    def __init__(self):
        self.exchange = None
        self.nonce = 1471033830007660


# Создание пустого декоратора
pass_context = click.make_pass_decorator(Context, ensure=True)


# Создание группы команд
@click.group()
@pass_context
def main(ctx):
    """Console script for cointrader on the Poloniex exchange
    :param ctx:
    """
    init_db()
    config = Config(open(get_path_to_config(), "r"))
    # for attempt in range(1,3):
    to_do = True
    while to_do:
        try:
            ctx.exchange = Poloniex(config, ctx.nonce)
            to_do = False
        except Exception as ex:
            if str(ex).split(" "):
                if str(ex).split(" ")[0] == 'Nonce':
                    ctx.nonce = int(str(ex).split(" ")[5][:-1]) + 1
            click.echo(ex)
            time.sleep(1)
            # sys.exit(1)


# Добавляем команды
@click.command()
@click.argument("market")
@click.option("--resolution", help="Resolution of the chart which is used for trend analysis", default="30m")
@click.option("--automatic", help="Start cointrader in automatic mode.", is_flag=True)
@click.option("--strategy", help="Stratgegy used for trading.", default="trend", type=click.Choice(STRATEGIES.keys()))
@click.option("--verbose", help="Вывод на экран логируемых сообщений.", is_flag=False)
@click.option("--percent", help="Процент торговли от всей суммы.", is_flag=False)
@click.option("--best", help="", is_flag=False)
@click.option("--searchpoint", help="", is_flag=False)
@click.option("--btc", help="trading value of BTC", default=0.0, type=float)
# @click.option("--best_pass_nth", help="", default="0")
@pass_context
def start(ctx, market, resolution, automatic, strategy, verbose, percent, best, searchpoint, btc):
    """Start a new bot on the given market and the given amount of BTC"""

    # Build the market on which the bot will operate
    # First check if the given market is a valid market. If not exit
    # here with a error message.
    # If the market is valid create a real market instance of and
    # instance for backtests depending on the user input.
    market = set_market(ctx, market, backtrade=False)

    # Check if the given resolution is supported
    if not ctx.exchange.is_valid_resolution(resolution):
        valid_resolutions = ", ".join(ctx.exchange.resolutions.keys())
        click.echo("Resolution {} is not supported.\n"
                   "Please choose one of the following: {}".format(resolution,
                                                                   valid_resolutions))
        sys.exit(1)

    # Initialise a strategy.
    strategy = STRATEGIES[strategy]()

    start, end = set_start_end()

    best_pair, best_testing_market = find_best_pair(automatic, ctx, end, market, percent, resolution, start, strategy,
                                                    verbose, searchpoint, btc)

    trade_to_minus = False
    # if int(best_pass_nth) == 0:
    if not best_testing_market:
        trade_to_minus = True
    elif best_pair != None:
        if best and not is_active(best_pair["market"]):
            print("\nВыбрана пара: %s, заработок: %f" % (best_pair["market"]._name, best_pair["profit"]))
            best_pair["market"]._backtrade = False
            bot = get_bot(best_pair["market"], strategy, resolution, start, end, verbose, percent, automatic,
                          memory_only=False, btc=btc)
            trade_to_minus = bot.start(backtest=False, automatic=automatic)

    elif best_testing_market[-1]["profit"] > 3 and not best and not is_active(best_testing_market[-1]["market"]):
        best_testing_market[-1]["market"]._backtrade = False
        bot = get_bot(best_testing_market[-1]["market"], strategy, resolution, start, end, verbose, percent, automatic,
                      memory_only=False, btc=btc)
        trade_to_minus = bot.start(backtest=False, automatic=automatic)

    if trade_to_minus:
        print("На данной паре заработок отсутсвует.")

    if best:
        to_do = True
    elif trade_to_minus:
        to_do = True
    else:
        to_do = False

    if to_do:

        while to_do:
            if trade_to_minus:
                best_pair, best_testing_market = find_best_pair(automatic, ctx, end, market, percent, resolution, start,
                                                                strategy,
                                                                verbose, searchpoint, btc=btc)
            for item in best_testing_market:
                item["market"]._backtrade = False
                if not is_active(item["market"]):
                    print("\nВыбрана пара: %s, заработок: %f" % (item["market"]._name, item["profit"]))
                    bot = get_bot(item["market"], strategy, resolution, start, end, verbose, percent, automatic,
                                  memory_only=False, btc=btc)
                    to_do = bot.start(backtest=False, automatic=automatic)

            trade_to_minus = True


def is_active(market):
    activities = db.query(Active).filter(Active.currency == market._name)
    if activities == None:
        return False
    else:
        return True


def find_best_pair(automatic, ctx, end, market, percent, resolution, start, strategy, verbose, searchpoint, btc):
    test_markets = []
    bot = get_bot(market, strategy, resolution, start, end, verbose, percent, automatic, memory_only=False, btc=btc)
    df = pd.DataFrame.from_dict(bot._market._exchange.markets, orient='index')
    if len(df):
        while not test_markets:
            mask = (df['volume'] > 50) & (df['change'] > -15) & (df['change'] < 3)
            test_markets = print_top_trends(ctx, df, market, backtrade=False, searchpoint=searchpoint, mask=mask)
            if not test_markets:
                time.sleep(1)
                print("Ищу пары по условию: (df['volume'] > 50) & (df['change'] > -15) & (df['change'] < 3)")

    try:
        for active in bot.activity:
            db.delete(active)

        db.delete(bot)
        db.commit()
    finally:
        pass
    best_testing_market = []
    test_markets.append(set_market(ctx, market._name, backtrade=True))
    index = 0
    for current_market in test_markets:
        if index > 5:
            break
        bot = create_bot(current_market, strategy, resolution, start, end, verbose, percent, automatic=True, btc=btc)
        for trade in bot.trades:
            try:
                if trade != bot.trades[0]:
                    db.delete(trade)
            except:
                pass
        if bot.spread > 0.5:
            print("Валюта {} имеет порог покупки {:.2f}%, будет пропущена.".format(bot.market.currency, bot.spread))
            continue

        bot.start(backtest=True, automatic=True)
        try:
            for active in bot.activity:
                db.delete(active)

            db.delete(bot)
            db.commit()
        finally:
            pass
        if bot.profit > 3 and bot.trend != 'Рынок ВВЕРХ':
            best_testing_market.append({"market": bot._market, "profit": bot.profit})
            index += 1
    from operator import itemgetter
    best_testing_market = sorted(best_testing_market, key=itemgetter('profit'), reverse=True)
    best_pair = best_markets_print(best_testing_market)
    return best_pair, best_testing_market


def best_markets_print(best_testing_market):
    best_pair = None
    out = [["ПАРА", "ЗАРАБОТОК"]]
    for item in best_testing_market:
        if item["profit"] > 0:
            if best_pair == None:
                best_pair = item
            elif item["profit"] > best_pair["profit"]:
                best_pair = item
            values = []
            values.append(item["market"]._name)
            values.append(round(item["profit"], 2))
            out.append(values)
    table = AsciiTable(out).table
    print("\n".join(["\nПрибыльные пары:", table]))
    return best_pair


def print_top_trends(ctx, df, market, backtrade, searchpoint, mask):
    df['change'] = df.change.astype(float)
    df['volume'] = df.volume.astype(float)
    df_filtered = df[mask]
    df_filtered = df_filtered.sort_values(by=['change'], ascending=searchpoint)
    test_markets = []
    out = [["ПАРА", "ОБЪЕМ", "ИЗМЕНЕНИЯ"]]
    for current_market, row in df_filtered.iterrows():
        volume, change = (row['volume'], row['change'])
        values = []
        values.append(current_market)
        values.append(volume)
        values.append(str(change) + "%")
        out.append(values)

        if current_market != market._name:
            test_markets.append(set_market(ctx, current_market, backtrade=True))
    table = AsciiTable(out).table
    print("\n".join(["\nРастущий тренд:", table]))
    return test_markets


def set_market(ctx, market, backtrade):
    if ctx.exchange.is_valid_market(market):
        market = Market(ctx.exchange, market, backTrade=backtrade)
    else:
        click.echo("Market {} is not available".format(market))
        sys.exit(1)
    return market


def set_start_end():
    try:
        now_time = datetime.now()
        delta = timedelta(days=1)
        date_N_days_ago = now_time - delta

        start = date_N_days_ago
        end = now_time
    except ValueError:
        click.echo("Days is not valid. Must be in 1 2 34 ...'")
        sys.exit(1)
    return start, end


main.add_command(start)

# Запуск сценария
if __name__ == "__main__":
    main()
