import datetime
from termcolor import colored
from terminaltables import AsciiTable


def colorize_value(value):
    if value < 0:
        return colored(value, "red")
    else:
        return colored(value, "green")


# def render_signal_details(signals):
#     out = [["Indicator", "Signal", "Details"]]
#     for s in signals:
#         out.append([s, signals[s].value, signals[s].details])
#     table = AsciiTable(out).table
#     return "\n".join(["\nSignal:", table])

def render_signal_detail(signal):
    if signal.buy:
        return colored("BUY", "green")
    if signal.sell:
        return colored("SELL", "red")
    else:
        return "WAIT"


def render_user_options(options):
    out = []
    for o in options:
        out.append("{}) {}".format(o[0], o[1]))
    return "\n".join(out)


def render_bot_title(bot, market, chart):

    out = ["\n"]
    data = chart._data

    if len(data) > 1:
        last = data[-2]
    else:
        last = data[-1]
    current = data[-1]

    values = {}
    values["date"] = datetime.datetime.utcfromtimestamp(current["date"])
    if current["close"] > last["close"]:
        values["rate"] = colored(current["close"], "green")
    else:
        values["rate"] = colored(current["close"], "red")
    change_percent = (current["close"] - last["close"]) / current["close"] * 100

    values["change_percent"] = round(change_percent, 4)
    values["url"] = market.url
    # # Если указаны монеты тогда выводим
    # if bot.coins:
    #     values["_amount_deleted"] = bot.coins
    # else:
    #     values["_amount_deleted"] =  bot._amount_deleted
    #
    # if bot.min_count_currency > 0 and values["_amount_deleted"] < bot.min_count_currency:
    #     values["_amount_deleted"] = bot.min_count_currency
    #
    balances = market._exchange.get_balance()
    values["amount"] = balances[market.currency]["quantity"]
    #
    # if bot.coins and amount - bot.coins < 0:
    #     print("Для торговли запрошено %.6f монет, а в наличии, только %.6f." % (bot.coins, bot.amount))
    # values["bot"] = bot.

    values["currency"] = market.currency
    t = u"{date} [{amount} {currency}] | {rate} ({change_percent}%) | {url}".format(**values)
    out.append("=" * len(t))
    out.append(t)
    out.append("=" * len(t))

    return "\n".join(out)


def render_bot_statistic(self, stat):
    out = [["", stat["start"], stat["end"], "Изменение %"]]
    out.append(["Бот", stat["trader_start_value"], stat["trader_end_value"], "{}".format(colorize_value(round(stat["profit_cointrader"], 4)))])
    out.append(["Биржа", stat["market_start_value"], stat["market_end_value"], "{}".format(colorize_value(round(stat["profit_chart"], 4)))])
    table = AsciiTable(out).table
    self.profit = stat["profit_cointrader"]

    return "\n".join(["\nСтатистика:", table])


def render_bot_tradelog(trades):
    out = [["ДАТА", "ТИП", "ЦЕНА", "МОНЕТЫ", "МОНЕТЫ'", "Биткоины", "Биткоины'"]]
    for trade in trades:
        values = []
        values.append(trade.date)
        values.append(trade.order_type)
        values.append(trade.rate)
        if trade.order_type == "BUY":
            values.append("--")
            values.append(trade.amount_taxed)
            values.append(trade.btc)
            values.append("--")
        elif trade.order_type == "SELL":
            values.append(trade.amount)
            values.append("--")
            values.append("--")
            values.append(trade.btc_taxed)
        else:
            values.append(trade.amount)
            values.append("--")
            values.append(trade.btc)
            values.append("--")
        out.append(values)
    table = AsciiTable(out).table

    return "\n".join(["\n:Журнал сделок:", table])
