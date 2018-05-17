import datetime
import os

import numpy as np
from scipy import optimize

from performance.models import DigitalTakeup


def date_to_curve_point(d):
    # normalise a month to integer: January 2017 -> 1
    return (d.year - 2017) * 12 + d.month


def curve_point_to_date(x):
    year, month = divmod(x - 1, 12)
    month += 1
    return datetime.date(year, month, 1)


class Curve:
    def __init__(self, key, default_params):
        path = os.path.join(os.path.dirname(__file__), 'predicted-curves', key + '.pickle')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                self.params = np.load(f)
        else:
            self.params = default_params

    def save_params(self, key):
        path = os.path.join(os.path.dirname(__file__), 'predicted-curves')
        os.makedirs(path, exist_ok=True)
        path = os.path.join(path, key + '.pickle')
        with open(path, 'wb') as f:
            self.params.dump(f)

    def get_value(self, x):
        raise NotImplementedError

    def error(self, params, x, y):
        self.params = params
        return y - self.get_value(x)

    def optimise(self, initial_params, x, y):
        results = optimize.leastsq(
            self.error,
            initial_params,
            args=(x, y)
        )
        self.params = results[0]


class Hyperbolic(Curve):
    # tends towards 0
    # ∝ 1/x

    def get_value(self, x):
        return self.params[0] / (x + self.params[1])


class Logarithmic(Curve):
    # monotonically increasing
    # ∝ log(x)

    def get_value(self, x):
        return self.params[0] * np.log(self.params[1] * x + self.params[2])


known_curves = {
    'accurate_credits_by_mtp': {
        'curve': Logarithmic,
        'defaults': np.array([8203.01875499, 93.74114044, -30.66596447], dtype='float64')
    },
    'extrapolated_credits_by_post': {
        'curve': Hyperbolic,
        'defaults': np.array([607678.489, 10.1228151], dtype='float64'),
    },
}


def load_curve(key):
    default_params = known_curves[key]['defaults']
    return known_curves[key]['curve'](key, default_params)


def train_curve(key, x, y):
    curve = load_curve(key)
    curve.optimise(curve.params, x, y)
    curve.save_params(key)
    return curve


def train_digital_takeup():
    rows = [
        (
            date_to_curve_point(row['date']),
            row['accurate_credits_by_mtp'],
            row['reported_credits_by_post'],
            row['reported_credits_by_mtp'],
        )
        for row in DigitalTakeup.objects.digital_takeup_per_month(since=DigitalTakeup.reports_start)
    ]
    rows = np.array(rows, dtype='int64')
    x = rows[..., 0]
    accurate_credits_by_mtp = rows[..., 1]
    train_curve('accurate_credits_by_mtp', x, accurate_credits_by_mtp)

    reported_credits_by_post = rows[..., 2]
    reported_credits_by_mtp = rows[..., 3]
    extrapolated_credits_by_post = (
        reported_credits_by_post * accurate_credits_by_mtp / reported_credits_by_mtp
    ).round().astype('int64')
    train_curve('extrapolated_credits_by_post', x, extrapolated_credits_by_post)
