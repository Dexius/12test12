#!/usr/bin/env python
import datetime
import logging
import string

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

    def signal(self, chart, verbose=False):
        self.verbose = verbose
        """Will return either a BUY, SELL or WAIT signal for the given
        market"""
        raise NotImplementedError


class NullStrategy(Strategy):
    """The NullStrategy does nothing than WAIT. It will emit not BUY or
    SELL signal and is therefor the default strategy when starting
    cointrader to protect the user from loosing money by accident."""

    def signal(self, chart, verbose=False):
        """Will return either a BUY, SELL or WAIT signal for the given
        market"""
        self.verbose = verbose
        signal = Signal(WAIT, datetime.datetime.utcnow())
        self.signals["WAIT"] = signal
        return signal


class Klondike(Strategy):

    def signal(self, chart, verbose=False):
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
        self.EMA = []
        self.trend = []

    def signal(self, chart, verbose=False, first_buy_price=1000000, backtest=False, backtest_tick=0):

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
        print("P: {:.5e} MACD: {:+.0f}".format(self._value, self._macd), end=" ", flush=True)

        # Finally we are using the double_cross signal as confirmation
        # of the former MACDH signal
        dc_signal = double_cross(current_strategy=self, chart=chart)

        list = chart.rsi()
        list_wr = chart.wr()
        list_dmi = chart.dmi()
        print(" ADX: {:+.2f}".format(list_dmi[-1]), end=" ", flush=True)
        good_to_sell = (list_wr[-1] > 63 and first_buy_price < self._value)
        good_to_buy = list[-1] < 63 and list_dmi[-1] > 20


        # if self._macd == BUY and dc_signal.value == BUY:
        #     print("----->{}".format(list[-1]))

        if (self.EMA[-2] >= 0 > self.EMA[-1] or self.EMA[-2] < 0 <= self.EMA[-1]) \
            and ((self._macd == BUY and dc_signal.value == BUY and good_to_buy)
                or
                (self._macd == SELL and dc_signal.value == SELL)):
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
        #     print("Итоговый сигнал @{}: {}".format(signal.date, signal.value), end="\n")

        log.debug("P: {:.5f} MACD+DC {}: {}".format(self._value, signal.date, signal.value))
        self.signals["DC"] = signal
        if list[-1] > 70:
            signal.over_sell = True
            SELL_ZONE += 1
            print(" SELL_ZONE: {:.2f}".format(SELL_ZONE, self._value), end=" ", flush=True)
        else:
            print(" BUY_ZONE: {:.2f} ".format(list[-1]), end=" ", flush=True)
        #
        if signal.value == SELL:
            SELL_ZONE = 0

        only_closes = []
        if backtest:
            current_chart = chart.data[120 - 3:backtest_tick]
        else:
            if len(chart.data) >= 2:
                current_chart = chart.data[:-2]
            else:
                current_chart = chart.data
        for x in current_chart[:-2]:
            only_closes.append(x["close"])

        if current_chart:
            last_max, last_min = self.FindMaximaMinima(numbers=only_closes)
            report = ""
            current_price = current_chart[-1]['close']
            if last_max:
                if len(last_max) == 1:
                    last_max = last_max[-1]
                else:
                    last_max = max(last_max)
                    if current_price > last_max:
                        report = report + "Пробитие локального МАКСИМУМА "

            if last_min:
                if len(last_min) == 1:
                    last_min = last_min[-1]
                else:
                    last_min = min(last_min)
                    if current_price < last_min:
                        report = report.join("Пробитие локального МИНИМУМА")

        if report:
            print(report, end=" ", flush=True)


        return signal

    """
    Find All Local Maximums and Minimums in a list of Integers.
    An element is a local maximum and minimums if it is larger than the two elements adjacent to it, or if it is the first or last element and larger than the one element adjacent to it.
    Design an algorithm to find all local maxima and mimima if they exist.
    Example:  for 3, 2, 4, 1 the local maxima are at indices 0 and 2.  
    """
    def FindMaximaMinima(self, numbers: list):

        maxima = []
        minima = []
        length = len(numbers)
        if length >= 2:
            if numbers[0] > numbers[1]:
                maxima.append(numbers[0])
            else:
                minima.append(numbers[0])

            if length > 3:
                for i in range(1, length - 1):
                    if numbers[i] > numbers[i - 1] and numbers[i] > numbers[i + 1]:
                        maxima.append(numbers[i])
                    elif numbers[i] < numbers[i - 1] and numbers[i] < numbers[i + 1]:
                        minima.append(numbers[i])

            if numbers[length - 1] > numbers[length - 2]:
                maxima.append(numbers[length - 1])
            elif numbers[length - 1] < numbers[length - 2]:
                minima.append(numbers[length - 1])
        return maxima, minima

