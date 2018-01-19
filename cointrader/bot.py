# -*- coding: utf-8 -*-
import select

import sys
import datetime
import time
import logging
import sqlalchemy as sa
import click
import pandas as pd
from cointrader import Base, engine, db
from cointrader.asset_fond import asset_fond
from cointrader.indicators import (
    WAIT, BUY, SELL, Signal, signal_map
)
from cointrader.helpers import (
    render_bot_statistic, render_bot_tradelog,
    render_bot_title, render_signal_detail,
    render_user_options
)

TIMEOUT = 0
# Number of seconds the bot will wait for user input in automatic mode
# to reattach the bot

log = logging.getLogger(__name__)


def replay_tradelog(trades, market, _market):
    btc = 0
    amount = 0
    for t in trades:
        if t.order_type == "INIT":
            btc = t.btc
            amount = t.amount
        elif t.order_type == "BUY":
            btc -= t.btc
            amount += t.amount
        else:
            btc += t.btc
            amount -= t.amount

    return btc, amount


def init_db():
    Base.metadata.create_all(engine)


def load_bot(market, strategy, resolution, start, end, verbose, percent, automatic, memory_only):
    """Will load an existing bot from the database. While loading the
    bot will replay its trades from the trade log to set the available _btc_deleted
    and coins for further trading.

    Beside the _btc_deleted and of coins all other aspects of the coin
    like the time frame and strategy are defined by the user. They are
    not loaded from the database."""
    try:
        bot = db.query(Cointrader).filter(Cointrader.market == market._name).one()
        bot.verbose = verbose
        if bot.verbose:
            print("Загружаем бота {} {}".format(bot.market, bot.id))
        log.info("Загружаем бота {} {}".format(bot.market, bot.id))
        bot._market = market
        bot._strategy = strategy
        bot._resolution = resolution
        bot._start = start
        bot._end = end
        bot._min_count_btc_deleted = 0.0
        bot._min_count_currency_deleted = 0.0
        bot._percent_deleted = float(percent)
        bot.detouch = False
        bot.fond = asset_fond(market, percent=percent)

        bot.strategy = str(strategy)
        btc, amount = replay_tradelog(bot.trades, market, bot._market)
        if bot.verbose:
            print("Восстановлен из журнала обмена: {} биткоинов {} монет".format(btc, amount))
        log.info("Восстановлен из журнала обмена: {} биткоинов {} монет".format(btc, amount))
        bot._btc_deleted = btc
        bot._amount_deleted = amount
        bot.profit = 0

        # # Добавляем список активных торгов
        # bot.active_trade_signal = []

        db.commit()
        return bot
    except sa.orm.exc.NoResultFound:
        return None


def create_bot(market, strategy, resolution, start, end, verbose, percent, automatic):
    """Will create a new bot instance."""
    bot = Cointrader(market, strategy, resolution, start, end, automatic, percent)
    bot.verbose = verbose
    if bot.verbose:
        print("Создаю нового бота {}".format(bot.market))
    log.info("Создаю нового бота {}".format(bot.market))

    # bot._percent_deleted = float(percent)
    # Setup the bot with coins and BTC.
    # amount, btc = get_balance_amount_btc(market)
    # bot._btc_deleted = btc / 100 * bot._percent_deleted
    # bot._amount_deleted = amount  # / 100 * bot._percent_deleted
    # bot._min_count_btc_deleted = 0.0
    # bot._min_count_currency_deleted = 0.0
    bot.detouch = False

    chart = market.get_chart(resolution, start, end)
    rate = chart.get_first_point()["close"]
    date = datetime.datetime.utcfromtimestamp(chart.get_first_point()["date"])

    trade = Trade(date, "INIT", 0, 0, market._name, rate, bot.fond.amount_btc, 0, bot.fond.btc, 0)
    bot.trades.append(trade)

    # # Добавляем список активных торгов
    # bot.active_trade_signal = []

    db.add(bot)
    db.commit()
    return bot


def get_balance_amount_btc(market):
    # Setup the bot with coins and BTC.
    balances = market._exchange.get_balance()
    btc = balances["BTC"]["quantity"]
    amount = balances[market.currency]["quantity"]

    return amount, btc


def get_bot(market, strategy, resolution, start, end, verbose, percent, automatic, memory_only):
    """Will load or create a bot instance.
    The bot will operate with the given `resolution` on the `market` using
    the specified `strategy`.

    The `start` and `end`
    The bot is equipped with a specified `_amount_deleted` of coins and  `_btc_deleted` for
    trading. If no _btc_deleted or _amount_deleted is specified (None), the bot will be
    initialised with *all* available coins on the given market.

    :market: :class:`Market` instance
    :strategy: :class:`Strategy` instance
    :resolution: Resolution in seconds the bot will operate on the market.
    :start: Datetime where the bot will start to operate
    :end: Datetime where the bot will end to operate
    :_btc_deleted: Amount of BTC the Bot will be initialised with
    :_amount_deleted: Amount of Coins (eg. Dash, Ripple) the Bot will be initialised with = coins
    :fixcoin Использован параметр *--coins*
    :coins значение параметра *--coins* X
    :verbose вывод логов на экран
    :returns:
    """

    if percent == None:
        percent = 100
    bot = load_bot(market, strategy, resolution, start, end, verbose, percent, automatic, memory_only)
    if bot is None:
        bot = create_bot(market, strategy, resolution, start, end, verbose, percent, automatic)
    return bot


class Trade(Base):
    """All trades of cointrader are saved in the database. A trade can either be a BUY or SELL."""
    __tablename__ = "trades"
    id = sa.Column(sa.Integer, primary_key=True)
    bot_id = sa.Column(sa.Integer, sa.ForeignKey('bots.id'))
    date = sa.Column(sa.DateTime, nullable=False, default=datetime.datetime.utcnow)
    order_type = sa.Column(sa.String, nullable=False)
    order_id = sa.Column(sa.Integer, nullable=False)
    trade_id = sa.Column(sa.Integer, nullable=False)
    market = sa.Column(sa.String, nullable=False)
    rate = sa.Column(sa.Float, nullable=False)

    amount = sa.Column(sa.Float, nullable=False)
    amount_taxed = sa.Column(sa.Float, nullable=False)
    btc = sa.Column(sa.Float, nullable=False)
    btc_taxed = sa.Column(sa.Float, nullable=False)

    def __init__(self, date, order_type, order_id, trade_id, market, rate, amount, amount_taxed, btc, btc_taxed):
        """Initialize a new trade log entry.

        :bot_id: ID of the bot which initiated the trade
        :date: Date of the order
        :order_id: ID of the order
        :order_type: Type of order. Can be either "BUY, SELL"
        :trade_id: ID of a single trade within the order
        :market: Currency_pair linke BTC_DASH
        :rate: Rate for the order
        :_amount_deleted: How many coins sold
        :amount_taxed: How many coins bought (including fee) order
        :_btc_deleted: How many payed on buy
        :btc_taxed: How many BTC get (including fee) from sell

        """
        if not isinstance(date, datetime.datetime):
            self.date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
        else:
            self.date = date
        self.order_type = order_type
        self.order_id = order_id
        self.trade_id = trade_id
        self.market = market
        self.rate = rate
        self.amount = amount
        self.amount_taxed = amount_taxed
        self.btc = btc
        self.btc_taxed = btc_taxed
        self.minimal_count = 0
        if self.order_type == "BUY":
            print("{}: BUY {} @ {} paid -> {} BTC".format(self.date, self.amount, self.rate, self.btc))
            log.info("{}: BUY {} @ {} paid -> {} BTC".format(self.date, self.amount, self.rate, self.btc))
        elif self.order_type == "SELL":
            print("{}: SELL {} @ {} earned -> {} BTC".format(self.date, self.amount, self.rate, self.btc))
            log.info("{}: SELL {} @ {} earned -> {} BTC".format(self.date, self.amount, self.rate, self.btc))
        else:
            print("{}: INIT {} BTC {} COINS".format(self.date, self.btc, self.amount))
            log.info("{}: INIT {} BTC {} COINS".format(self.date, self.btc, self.amount))


class Cointrader(Base):
    """Cointrader"""
    __tablename__ = "bots"
    id = sa.Column(sa.Integer, primary_key=True)
    created = sa.Column(sa.DateTime, nullable=False, default=datetime.datetime.utcnow)
    active = sa.Column(sa.Boolean, nullable=False, default=True)
    market = sa.Column(sa.String, nullable=False)
    strategy = sa.Column(sa.String, nullable=False)
    automatic = sa.Column(sa.Boolean, nullable=False)
    trades = sa.orm.relationship("Trade")

    def __init__(self, market, strategy, resolution="30m", start=None, end=None, automatic=False, percent=100):

        self.verbose = False
        self.market = market._name
        self.strategy = str(strategy)
        self.automatic = automatic

        self._market = market
        self._strategy = strategy
        self._resolution = resolution
        self._start = start
        self._end = end

        self._amount_deleted = 0
        self._btc_deleted = 0
        self.fond = asset_fond(market, percent=percent)
        self.detouch = False
        self.profit = 0
        # The bot has either _btc_deleted to buy or _amount_deleted of coins to sell.

    def get_last_sell(self):
        for t in self.trades[::-1]:
            if t.order_type == "SELL":
                return t

    def get_last_buy(self):
        for t in self.trades[::-1]:
            if t.order_type == "BUY":
                return t

    def check_actual_amount(self, amount):
        actual_amount, btc = get_balance_amount_btc(self._market)
        if amount < actual_amount:
            print("Расчетная покупка: %s факт: %s" % (amount, actual_amount))
            return actual_amount

        return amount

    def _buy(self):
        # # Торгуем указанным количеством в парамтере *--coins*
        # if self.coins:
        #     _amount_deleted = self.test_min_value_btc(self.coins)
        # else:
        #     _amount_deleted = self.test_min_value_amount(self._amount_deleted)

        result = self._market.buy(self.fond.btc)
        # {u'orderNumber': u'101983568396',
        #  u'resultingTrades': [{u'tradeID': u'10337029',
        #                        u'rate': u'0.01459299',
        #                        u'_amount_deleted': u'0.01263972',
        #                        u'date': u'2017-08-28 19:51:50',
        #                        u'total': u'0.00018445', u'type': u'buy'}]}
        order_id = result["orderNumber"]
        order_type = "BUY"
        total_amount = 0

        if result and self.verbose:
            for trade in result['resultingTrades']:
                print("orderNumber: %s, операция: %s, всего: %s" % (order_id,
                                                                    trade['type'],
                                                                    trade['total']
                                                                    ))

        for t in result["resultingTrades"]:
            trade_id = t["tradeID"]
            date = t["date"]
            amount = float(t["amount"])
            total_amount += float(amount)
            rate = float(t["rate"])
            btc = float(t["total"])
            trade = Trade(date, order_type, order_id, trade_id, self._market._name, rate, btc_taxed=0,
                          btc=self.fond.btc, amount_taxed=0, amount=total_amount)
            self.trades.append(trade)

        self.fond.add_row(btc=self.fond.btc, amount_btc=total_amount, order_type=order_type)

        # Finally set the internal state of the bot. BTC will be 0 after
        # buying but we now have some _amount_deleted of coins.
        self.fond.amount_btc = total_amount
        self.fond.btc = 0.0
        self.state = 1
        db.commit()

    def _sell(self, amount_btc=0, first_sell=False):
        global renew
        # # Торгуем указанным количеством в парамтере *--coins*
        # if self.coins:
        #     _amount_deleted = self.test_min_value_btc(self.coins)
        # else:
        #     _amount_deleted = self.test_min_value_btc(self._amount_deleted)

        if amount_btc == 0:
            amount_btc = self.fond.amount_btc
            renew = True
        else:
            amount_btc = amount_btc

        result = self._market.sell(amount_btc)
        # {u'orderNumber': u'101984509454',
        #  u'resultingTrades': [{u'tradeID': u'10337105',
        #                        u'rate': u'0.01458758',
        #                        u'_amount_deleted': u'0.01263972',
        #                        u'date': u'2017-08-28 19:57:51',
        #                        u'total': u'0.00018438',
        #                        u'type': u'sell'}]}
        order_id = result["orderNumber"]
        order_type = "SELL"
        total_btc = 0.0

        if result and self.verbose:
            for trade in result['resultingTrades']:
                print("orderNumber: %s, операция: %s, всего: %s" % (order_id,
                                                                    trade['type'],
                                                                    trade['total']
                                                                    ))

        for t in result["resultingTrades"]:
            trade_id = t["tradeID"]
            date = t["date"]
            amount = float(t["amount"])
            rate = float(t["rate"])
            btc = float(t["total"])
            total_btc += float(btc)
            trade = Trade(date, order_type, order_id, trade_id, self._market._name, rate,
                          btc_taxed=0, btc=total_btc, amount_taxed=0, amount=amount)
            self.trades.append(trade)

        self.fond.add_row(btc=total_btc, amount_btc=btc, order_type=order_type, first_sell=first_sell,
                          renew=True)

        # Finally set the internal state of the bot. Amount will be 0 after
        # selling but we now have some BTC.
        self.state = 0.0
        db.commit()

    def get_stop_limit(cls):
        for item in cls.fond.rows:
            if item["order_type"] == "BUY":
                return item["btc"] / item["amount_btc"]


    def test_min_value_btc(self, btc):
        if not (self._min_count_btc_deleted == 0.0 and self._min_count_btc_deleted < btc) and self.verbose:
            print("Установлен минимальное доступное количество %f" % self._min_count_btc_deleted)
            btc = self._min_count_btc_deleted
        return btc

    def test_min_value_amount(self, amount):
        if not (self._min_count_currency_deleted == 0 and self._min_count_currency_deleted < amount) and self.verbose:
            print("Установлен минимальное доступное количество %f" % self._min_count_currency_deleted)
            amount = self._min_count_btc_deleted
        return amount

    def stat(self, delete_trades=False):
        """Returns a dictionary with some statistic of the performance
        of the bot.  Performance means how good cointrader performs in
        comparison to the market movement. Market movement is measured
        by looking at the start- and end rate of the chart.

        The performance of cointrader is measured by looking at the
        start and end value of the trade. These values are also
        multiplied with the start and end rate. So if cointrader does
        some good decisions and increases eater _btc_deleted or _amount_deleted of coins
        of the bot the performance should be better."""

        global trader_start_btc, trader_start_amount, market_start_btc, market_start_amount
        chart = self._market.get_chart(self._resolution, self._start, self._end)

        first = chart.get_first_point()
        market_start_rate = first["close"]
        start_date = datetime.datetime.utcfromtimestamp(first["date"])

        last = chart.get_last_point()
        market_end_rate = last["close"]
        end_date = datetime.datetime.utcfromtimestamp(last["date"])

        # Set start value
        for trade in self.trades:
            if trade.order_type == "INIT":
                trader_start_btc = trade.btc
                trader_start_amount = trade.amount
                market_start_btc = trade.btc
                market_start_amount = trade.amount

        trader_end_btc = trader_start_btc
        trader_end_amount = trader_start_amount
        for trade in self.trades:
            if trade.order_type == "BUY":
                trader_end_amount += trade.amount
                trader_end_btc -= trade.btc
            elif trade.order_type == "SELL":
                trader_end_btc += trade.btc
                trader_end_amount -= trade.amount

        trader_start_value = trader_start_btc + trader_start_amount * market_start_rate
        market_start_value = trader_start_value
        trader_end_value = trader_end_btc + trader_end_amount * market_end_rate
        market_end_value = market_start_btc + market_start_amount * market_end_rate
        trader_profit = trader_end_value - trader_start_value
        market_profit = market_end_value - market_start_value

        profit_chart = 0.0
        if market_end_value:
            profit_chart = market_profit / market_end_value * 100

        profit_cointrader = 0.0
        if trader_end_value:
            profit_cointrader = trader_profit / trader_end_value * 100


        stat = {
            "start": start_date,
            "end": end_date,
            "market_start_value": market_start_value,
            "market_end_value": market_end_value,
            "profit_chart": profit_chart,
            "trader_start_value": trader_start_value,
            "trader_end_value": trader_end_value,
            "profit_cointrader": profit_cointrader,
        }
        if delete_trades:
            for trade in self.trades:
                try:
                    db.delete(trade)
                except:
                    pass
            db.commit()
        return stat

    def _in_time(self, date):
        return (self._start is None or self._start <= date) and (self._end is None or date <= self._end)

    def _get_interval(self, automatic, backtest):
        # Set number of seconds to wait until the bot again call for a
        # trading signal. This defaults to the resolution of the bot
        # which is provided on initialisation.
        if automatic and not backtest:
            interval = self._market._exchange.resolution2seconds(self._resolution)
        else:
            interval = 0
        return interval

    def _handle_signal(self, signal, backtest, chart, first_sell=False, memory_only=False):
        # global can_buy, can_sell
        result = 'No action'
        if not backtest:
            if signal.value == BUY or signal.value == SELL:

                # _amount_deleted, _btc_deleted = get_balance_amount_btc(self._market)
                # print("\nТекущий баланс: %f BTC %f COINS." % (_btc_deleted, _amount_deleted))
                #
                # # Минимальная торговая сделка
                # min_btc_trade = 0.0001
                # if signal.value == SELL:
                #     min_btc_trade = min_btc_trade + min_btc_trade * 0.0025
                # elif signal.value == BUY:
                #     min_btc_trade = min_btc_trade + min_btc_trade * 0.0015
                #
                # # Берем актуальную цену сделки
                # price = chart._data[-1]['close']
                # min_amount_trade = min_btc_trade / price
                #
                # can_buy = min_btc_trade < self._btc_deleted
                # if not can_buy and self._btc_deleted > 0:
                #     print('ПОКУПКА: Сумма меньше ограничения биржи и составляет: %f.' % self._btc_deleted)
                # can_sell = min_amount_trade < self._amount_deleted
                # if not can_sell and self._amount_deleted > 0:
                #     print('ПРОДАЖА: Сумма меньше ограничения биржи и составляет: %f.' % self._amount_deleted)

                self.fond.print_used_btc()

                if signal.value == BUY and self._in_time(signal.date) and self.fond.begin_tradind_test_amount_btc() \
                    and not self.fond.rows:
                    self._buy()
                    result = 'Buy'
                    # Выводим статистику
                    click.echo(render_bot_statistic(self, self.stat()))

                elif signal.value == SELL and self._in_time(
                    signal.date) and self.fond.begin_tradind_test_btc() and not first_sell:
                    self._sell()
                    result = 'Sell'
                    # Выводим статистику
                    click.echo(render_bot_statistic(self, self.stat()))
                elif first_sell:
                    closing = chart.values()
                    _value = closing[-1][1]
                    total_btc = self.fond.amount_btc * 0.1
                    total_amount = total_btc / _value
                    self._sell(total_amount, first_sell)
                    result = 'Sell'
                    # Выводим статистику
                    click.echo(render_bot_statistic(self, self.stat()))

        else:
            if (signal.value == BUY and self.fond.begin_tradind_test_amount_btc()) or (
                signal.value == SELL and self.fond.begin_tradind_test_btc()) or (
                first_sell and self.fond.amount_btc > 0):
                # Get current chart
                closing = chart.values()
                _value = closing[-1][1]
                _date = datetime.datetime.utcfromtimestamp(closing[-1][0])

                if signal.buy and not first_sell and not self.fond.rows:
                    order_type = "BUY"
                    total_amount = self.fond.btc / _value
                    trade = Trade(_date, order_type, '11111111', '111111111', self._market._name, _value, btc_taxed=0,
                                  btc=self.fond.btc, amount_taxed=0, amount=total_amount)
                    # Finally set the internal state of the bot. BTC will be 0 after
                    # buying but we now have some _amount_deleted of coins.
                    # self._amount_deleted = total_amount
                    # self.fond.btc = 0.0
                    # self.fond.amount_btc = total_amount * _value
                    self.fond.add_row(btc=self.fond.btc, amount_btc=total_amount, order_type=order_type,
                                      first_sell=first_sell)

                    self.state = 1
                    db.commit()
                    self.trades.append(trade)

                    # Выводим статистику
                    click.echo(render_bot_statistic(self, self.stat()))

                elif signal.sell and not first_sell:
                    order_type = "SELL"
                    total_amount = self.fond.amount_btc
                    total_btc = self.fond.btc + total_amount * _value
                    trade = Trade(_date, order_type, '22222222', '222222222', self._market._name, _value,
                                  btc_taxed=0, btc=total_btc, amount_taxed=0, amount=total_amount)

                    # Finally set the internal state of the bot. Amount will be 0 after
                    # selling but we now have some BTC.
                    self.state = 0
                    self.fond.add_row(btc=total_btc, amount_btc=total_amount, order_type=order_type,
                                      first_sell=first_sell, renew=True)
                    # self.fond.btc = total_btc
                    # self.fond.amount_btc = 0.0
                    db.commit()
                    self.trades.append(trade)

                    # Выводим статистику
                    click.echo(render_bot_statistic(self, self.stat()))

                elif first_sell:
                    order_type = "SELL"
                    total_btc = self.fond.amount_btc * 0.1
                    total_amount = total_btc / _value
                    trade = Trade(_date, SELL, '22222222', '222222222', self._market._name, _value,
                                  btc_taxed=0, btc=total_btc, amount_taxed=0, amount=total_amount)

                    # Finally set the internal state of the bot. Amount will be 0 after
                    # selling but we now have some BTC.
                    self.state = 0
                    self.fond.add_row(btc=total_btc, amount_btc=total_amount, order_type="SELL", first_sell=first_sell)
                    # self.fond.btc = total_btc
                    # self.fond.amount_btc = 0.0
                    db.commit()
                    self.trades.append(trade)

                    # Выводим статистику
                    click.echo(render_bot_statistic(self, self.stat()))

        stat = self.stat(memory_only)
        if round(stat['profit_cointrader'], 4) < -0.3:
            self.detouch = True

        return result

    def start(self, backtest=False, automatic=False, show_report=False, memory_only=False):
        """Start the bot and begin trading with given _amount_deleted of BTC.

        The bot will trigger a analysis of the chart every N seconds.
        The default number of seconds is set on initialisation using the
        `resolution` option. You can overwrite this setting
        by using the `interval` option.

        By setting the `backtest` option the trade will be simulated on
        real chart data. This is useful for testing to see how good
        your strategy performs.

        :_btc_deleted: Amount of BTC to start trading with
        :backtest: Simulate trading on historic chart data on the given market.
        :returns: None
        """

        interval = self._get_interval(automatic, backtest)
        chart_last = None
        while 1:
            if chart_last == None and not backtest and automatic:
                # self._start = None
                # self._end = None
                print("Синхронизируемся по времени свечи.")
                while 1:
                    if chart_last == None:
                        chart_last = self._market.get_chart(self._resolution, self._start, self._end).data[-1]['date']
                    if chart_last != self._market.get_chart(self._resolution, self._start, self._end).data[-1]['date']:
                        print("Синхронизация завершена.")
                        break
                    time.sleep(1)

            chart = self._market.get_chart(self._resolution, self._start, self._end)
            signal = self._strategy.signal(chart, self.verbose)
            closing = chart.values()
            _value = closing[-1][1]
            first_sell = self.first_sell(_value)
            # if self.verbose:
            #     print("{} {}".format(signal.date, signal_map[signal.value]))
            log.debug("{} {}".format(signal.date, signal_map[signal.value]))

            if not automatic:
                click.echo(render_bot_title(self, self._market, chart))
                click.echo(render_signal_detail(signal))

                options = []
                if self._btc_deleted:
                    options.append(('b', 'Buy'))
                if self._amount_deleted:
                    options.append(('s', 'Sell'))
                options.append(('l', 'Tradelog'))
                options.append(('p', 'Performance of bot'))
                if not automatic:
                    options.append(('d', 'Detach'))
                options.append(('q', 'Quit'))

                click.echo(render_user_options(options))
                c = input()
                if c == 'b' and self._btc_deleted:
                    if self.fond.begin_tradind_test_amount_btc():
                        signal = Signal(BUY, datetime.datetime.utcnow())
                elif c == 's' and self._amount_deleted:
                    if self.fond.begin_tradind_test_amount_btc():
                        # amount = self.fond.amount_btc
                        # else:
                        #     amount = self._min_count_currency_deleted
                        if click.confirm('Sell {}?'.format(self.fond.amount_btc)):
                            signal = Signal(SELL, datetime.datetime.utcnow())
                elif c == 'l':
                    click.echo(render_bot_tradelog(self.trades))
                elif c == 'p':
                    click.echo(render_bot_statistic(self, self.stat()))
                elif c == 'd':
                    automatic = True
                    if self.verbose:
                        print("Бот отключен")
                    log.info("Бот отключен")
                elif c == 'q':
                    if self.verbose:
                        print("Бот отключен")
                    log.info("Бот отключен")
                    sys.exit(0)
                else:
                    signal = Signal(WAIT, datetime.datetime.utcnow())

            if automatic:

                """ TODO: """

            if signal:
                # try:
                #     if not self.active_trade_signal:
                #         self.active_trade_signal.append(signal.value)

                if signal.value != WAIT or first_sell:

                    result = self._handle_signal(signal, backtest, chart, memory_only=memory_only,
                                                 first_sell=first_sell)
                    # self.active_trade_signal[0] = signal.value
                    if self.verbose and signal.value == BUY and result == 'Buy':
                        print("Произведена закупка")
                    elif self.verbose and signal.value == SELL and result == 'Sell':
                        print("Произведена продажа")
                    elif self.verbose and result == 'Enough':
                        if signal.value == SELL:
                            print("Не достаточно средств. ПРОДАЖА аннулирована.")
                        if signal.value == BUY:
                            print("Не достаточно средств. ПОКУПКА аннулирована.")

                    # # Записываем текущий активный сигнал в *active_trade_signal*
                    # self.active_trade_signal.append(signal.value)

            # except Exception as ex:
            #     # Выводим ошибку выполнения
            #     if self.verbose:
            #         print("Не могу разметить ордер: {}".format(ex))
            #     log.error("Не могу разметить ордер: {}".format(ex))
            #
            #     # Пробую вычислить лимит сделки в BTC
            #     try:
            #         if signal.value == BUY or signal.value == SELL:
            #             min_count_btc = float(str(ex).split(" ")[-1][:-1])
            #             self._min_count_btc_deleted = min_count_btc
            #
            #             # Берем актуальную цену сделки
            #             price = float(chart._data[-1]['close'])
            #
            #             # Устанавливаем минимальную цену сделки
            #             self._min_count_currency_deleted = self._min_count_btc_deleted / price
            #             self._min_count_currency_deleted = self._min_count_currency_deleted + self._min_count_currency_deleted * 0.02
            #
            #     except Exception as ex:
            #         print("Ошибка: " + str(ex))

            if self.detouch:
                print("Бот отключен из-за падения курса")
                break

            if backtest:

                if not self._market.continue_backtest():
                    if show_report:
                        data = chart.data
                        df = pd.io.json.json_normalize(data)
                        df['date'] = pd.to_datetime(df.date, unit='s')
                        df = df[['close', 'date', 'high', 'low', 'open', 'volume', 'weightedAverage']]

                        from stockstats import StockDataFrame
                        from bokeh.plotting import figure, show, output_notebook, output_file

                        from_symbol = 'BTC'
                        to_symbol = self._market.currency
                        exchange = 'Polonix'
                        datetime_interval = 'minute'
                        if self._resolution[-1] == "m":
                            datetime_interval = 'minute'
                        elif self._resolution[-1] == "h":
                            datetime_interval = 'hour'

                        df = StockDataFrame.retype(df)
                        df['macd'] = df.get('macd')
                        output_notebook()

                        datetime_from = datetime.datetime.strftime(self._start, "%Y.%m.%d %H:%M")
                        datetime_to = datetime.datetime.strftime(self._end, "%Y.%m.%d %H:%M")

                        df_limit = df[datetime_from: datetime_to].copy()
                        inc = df_limit.close > df_limit.open
                        dec = df_limit.open > df_limit.close

                        title = '%s datapoints from %s to %s for %s and %s from %s with MACD strategy' % (
                            datetime_interval, datetime_from, datetime_to, from_symbol, to_symbol, exchange)
                        p = figure(x_axis_type="datetime", plot_width=1000, title=title)

                        p.line(df_limit.index, df_limit.close, color='black')

                        # plot macd strategy
                        p.line(df_limit.index, 0, color='black')
                        p.line(df_limit.index, df_limit.macd, color='blue')
                        p.line(df_limit.index, df_limit.macds, color='orange')
                        p.vbar(x=df_limit.index, bottom=[
                            0 for _ in df_limit.index], top=df_limit.macdh, width=4, color="purple")

                        def get_candlestick_width(datetime_interval):
                            if datetime_interval == 'minute':
                                return 30 * 60 * 1000  # half minute in ms
                            elif datetime_interval == 'hour':
                                return 0.5 * 60 * 60 * 1000  # half hour in ms
                            elif datetime_interval == 'day':
                                return 12 * 60 * 60 * 1000  # half day in ms

                        # plot candlesticks
                        candlestick_width = get_candlestick_width(datetime_interval)
                        p.segment(df_limit.index, df_limit.high,
                                  df_limit.index, df_limit.low, color="black")
                        p.vbar(df_limit.index[inc], candlestick_width, df_limit.open[inc],
                               df_limit.close[inc], fill_color="#D5E1DD", line_color="black")

                        p.vbar(df_limit.index[dec], candlestick_width, df_limit.open[dec],
                               df_limit.close[dec], fill_color="#F2583E", line_color="black")
                        datetime_from = datetime.datetime.strftime(self._start, "%Y-%m-%d %H-%M")
                        datetime_to = datetime.datetime.strftime(self._end, "%Y-%m-%d %H-%M")
                        try:
                            output_file(("visualizing_trading_strategy_" + from_symbol + "_" + to_symbol +
                                         "_" + datetime_from + "_" + datetime_to + ".html"),
                                        title="visualizing trading strategy")
                        except:
                            pass

                        show(p)

                    if self.verbose:
                        print("Тестирование завершено")
                    log.info("Тестирование завершено")
                    break

            time.sleep(interval)

    def first_sell(self, price):
        first_sell_in_it = False
        for item in self.fond.rows:
            if item["order_type"] == "SELL" and item["first_sell"] == True:
                first_sell_in_it = True

        if not first_sell_in_it and self.fond.rows:
            return price > self.get_stop_limit() * .01

        return False
