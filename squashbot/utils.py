"""Utilities for making programming great again."""
import operator
import pendulum
import operator


def markdown_link(title, url):
    """Generates markdown link string."""
    return "[{}]({})".format(title, url)


def grouper(iterable, n):
    """Return list of lists group by n elements."""
    l = []
    bf = []
    for e in iterable:
        bf.append(e)
        if len(bf) == n:
            l.append(bf)
            bf = []
    if len(bf) > 0:
        l.append(bf)
    return l


def previous_days(n, before=None):
    """Return last n days before specified date."""
    before = before or pendulum.today()
    return (before - before.subtract(days=n)).range('days')


def custom_xrange(period, unit, step=1):
    """Implement Pendulum range function but with non-unit step."""
    method = 'add'
    op = operator.le
    if not period._absolute and period.invert:
        method = 'subtract'
        op = operator.ge
    start, end = period.start, period.end
    i = 1
    while op(start, end):
        yield start
        start = getattr(period.start, method)(**{unit: step * i})
        i += 1
