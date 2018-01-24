import sys

from click._unicodefun import click
import cointrader.config
from cointrader.exchange import Poloniex


class asset_fond():
    def __init__(self, exchange, order_type="TOTAL", percent=100.0):

        # config = cointrader.config.Config(open(cointrader.config.get_path_to_config(), "r"))
        # try:
        #     self.exchange = Poloniex(config)
        # except Exception as ex:
        #     print(ex)
        #     sys.exit(1)

        self.order_type = order_type
        percent = self._tofloat(percent)

        self.exchange = exchange._exchange
        self.btc = self.get_btc(percent)
        self.currency_pair = exchange._name
        self.amount_btc = self.get_amount_btc(0.0, backtest=True)
        self.percent = percent
        self.minimal_step_cost = .00001 * 1.0025
        self.error = ""
        self.sell_percent = 0.0
        self.rows = []
        self.begin_tradind_test_btc()
        self.print_used_btc()

    def get_allow_sell(self, amount_to_sell, rate):
        if amount_to_sell * rate <= .00015:
            value = 1.00
            amount_to_sell_in_btc = amount_to_sell * rate
            while amount_to_sell_in_btc <= .00015:
                amount_to_sell_in_btc = amount_to_sell_in_btc * value
                value += 0.01
            return amount_to_sell_in_btc / rate
        else:
            return amount_to_sell

    def add_row(self, btc, amount_btc, order_type, first_sell=False, renew=False):
        if not self.rows:
            self.rows.append(self._row_dict(btc, self.get_amount_btc(amount_btc), "INIT", first_sell))
            self.rows.append(self._row_dict(btc, amount_btc, "BUY", first_sell))
            self.order_type = "TOTAL"
            self.btc = 0.0
            self.amount_btc = 0.0
            self.sell_percent = 0.0
        else:
            self.rows.append(self._row_dict(btc, amount_btc, order_type, first_sell))
        self.calculate()

        if renew:
            self.rows = []

    def _row_dict(self, btc, amount_btc, order_type, first_sell):
        return {"btc": btc, "amount_btc": amount_btc, "order_type": order_type, "first_sell": first_sell}

    def calculate(self):
        global buy_btc, sell_percent
        total_btc = 0
        total_amount_btc = 0
        sell_percent = 0.0
        for row in self.rows:
            if row["order_type"] == "SELL":
                total_btc += row["btc"]
                total_amount_btc -= row["amount_btc"]
                sell_percent = float("{0:.2f}".format(total_btc / (buy_btc * 0.01)))
            elif row["order_type"] == "BUY":
                total_btc -= row["btc"]
                total_amount_btc += row["amount_btc"]
            elif row["order_type"] == "INIT":
                total_btc = row["btc"]
                total_amount_btc = row["amount_btc"]
                buy_btc = total_btc

        self.btc = total_btc
        self.amount_btc = total_amount_btc
        self.sell_percent = sell_percent

    def _tofloat(self, percent):
        return float(percent)

    def print_balance(self):
        """Overview of your balances on the market."""
        click.echo("{:<4}  {:>12} {:>12}".format("CUR", "total", "btc_value"))
        click.echo("{}".format("-" * 31))
        coins = self.exchange.coins
        for currency in coins:
            click.echo("{:<4}: {:>12} {:>12}".format(currency, coins[currency].quantity, coins[currency].value))
        click.echo("{}".format("-" * 31))
        click.echo("{:<9}: {:>20}".format("TOTAL BTC", self.exchange.total_btc_value))
        click.echo("{:<9}: {:>20}".format("TOTAL USD", self.exchange.total_euro_value))
        click.echo("{:<9}: {:>20}".format("BTC price",
                                          round(self.exchange.total_euro_value / self.exchange.total_btc_value, 0)))

    def get_btc(self, percent):
        return self.exchange.coins['BTC'].btc_value / 100 * percent

    def get_amount_btc(self, amount_btc: float, backtest=False):
        if not backtest:
            try:
                amount_btc = self.exchange._api.balance()[self.currency_pair.split("_")[1]]['quantity']
            except:
                amount_btc = 0.0

        return amount_btc

    def print_used_btc(self):
        print("Торговая сумма на покупку BTC: {}".format(self.btc), end=" ")
        print("Общий баланс: {} BTC. {}: {}".format(self.exchange.total_btc_value, self.currency_pair.split("_")[-1], self.amount_btc))

    def begin_tradind_test_btc(self):
        if self.btc > self.minimal_step_cost:
            return True
        else:
            self.error = "Сумма покупки {} меньше минимально возможной для торговли {}.".format(self.btc,
                                                                                                self.minimal_step_cost)
            print(self.error)
            return False

    def begin_trading_test_amount_btc(self):
        # if self.amount_btc > self.minimal_step_cost:
            return True
        # else:
        #     self.error = "Сумма продажи {} меньше минимально возможной для торговли {}.".format(self.btc,
        #                                                                                         self.minimal_step_cost)
        #     print(self.error)
        #     return False

    def check_error(self):
        if self.error:
            print(self.error)

    def set_amount(self):
        price = self.exchange.coins[str(self.exchange._name).split("_")[-1]]["btc_value"]
        amount = self.btc / price
        self.begin_tradind_test_btc()
        self.check_error()

        return amount
