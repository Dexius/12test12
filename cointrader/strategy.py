#!/usr/bin/env python
import datetime
import logging
from cointrader.indicators import (
    SELL_ZONE, WAIT, BUY, SELL, Signal, macdh_momententum, macdh, double_cross
)

log = logging.getLogger(__name__)


class Strategy(object):

    """Docstring for Strategy. """

    def __str__(self):
        return "{}".format(self.__class__)

    def __init__(self):
        self.signals = {}
        self.verbose = False
        """Dictionary with details on the signal(s)
        {"indicator": {"signal": 1, "details": Foo}}"""

    def signal(self, chart, verbose = False):
        self.verbose = verbose
        """Will return either a BUY, SELL or WAIT signal for the given
        market"""
        raise NotImplementedError


class NullStrategy(Strategy):

    """The NullStrategy does nothing than WAIT. It will emit not BUY or
    SELL signal and is therefor the default strategy when starting
    cointrader to protect the user from loosing money by accident."""

    def signal(self, chart, verbose = False):
        """Will return either a BUY, SELL or WAIT signal for the given
        market"""
        self.verbose = verbose
        signal = Signal(WAIT, datetime.datetime.utcnow())
        self.signals["WAIT"] = signal
        return signal


class Klondike(Strategy):

    def signal(self, chart, verbose = False):
        self.verbose = verbose
        signal = macdh_momententum(chart)
        self.signals["MACDH_MOMEMENTUM"] = signal
        if signal.buy or signal.sell:
            return signal
        return Signal(WAIT, datetime.datetime.utcfromtimestamp(chart.date))


class Followtrend(Strategy):
    """Simple trend follow strategie."""


    def __init__(self):

        Strategy.__init__(self)
        self._macd = WAIT
        self.verbose = False

    def signal(self, chart, verbose=False, first_buy_price=777777777777777777777777777):

        global SELL_ZONE
        self.verbose = verbose
        # Get current chart
        closing = chart.values()

        self._value = closing[-1][1]
        self._date = datetime.datetime.utcfromtimestamp(closing[-1][0])

        # MACDH is an early indicator for trend changes. We are using the
        # MACDH as a precondition for trading signals here and required
        # the MACDH signal a change into a bullish/bearish market. This
        # signal stays true as long as the signal changes.
        macdh_signal = macdh(chart)
        if macdh_signal.value == BUY:
            self._macd = BUY
        if macdh_signal.value == SELL:
            self._macd = SELL
        log.debug("macdh signal: {}".format(self._macd))
        print("MACD histogram signal: {}".format(self._macd), end=" ", flush=True)

        # Finally we are using the double_cross signal as confirmation
        # of the former MACDH signal
        dc_signal = double_cross(chart)

        list = chart.rsi()
        list_wr = chart.wr()
        good_to_sell = (list_wr[-1] > 70 and first_buy_price < self._value)
        good_to_buy = list[-1] < 53

        # if self._macd == BUY and dc_signal.value == BUY:
        #     print("----->{}".format(list[-1]))

        if (self._macd == BUY and dc_signal.value == BUY and good_to_buy) or (
            self._macd == SELL and dc_signal.value == SELL):
            signal = dc_signal
            # print("Уровень 1: {}".format(list[-1]))
            # print("Уровень 2: {}".format(list_wr[-1]))
            # if list_wr[-1] > 70:
            #     print("Уровень 2: {}".format(list_wr[-1]))
        elif good_to_sell:
            signal = Signal(SELL, dc_signal.date)

        else:
            signal = Signal(WAIT, dc_signal.date)

        # if self.verbose:
        #     print("Итоговый сигнал @{}: {}".format(signal.date, signal.value), end="\n", flush=True)

        log.debug("Итоговый сигнал @{}: {}".format(signal.date, signal.value))
        self.signals["DC"] = signal
        if list[-1] > 70:
            signal.over_sell = True
            SELL_ZONE += 1
            print(" SELL_ZONE: {} Курс: {}".format(SELL_ZONE, self._value))
        else:
            print(" ")
        #
        if signal.value == SELL:
            SELL_ZONE = 0

        return signal
