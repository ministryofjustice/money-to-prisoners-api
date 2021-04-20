import datetime
import logging
import pathlib

from django.utils.timezone import now
import numpy as np
from scipy import optimize

from performance.models import DigitalTakeup

logger = logging.getLogger('mtp')


def date_to_curve_point(d):
    # normalise a month to integer: January 2017 -> 1
    return (d.year - 2017) * 12 + d.month


def curve_point_to_date(x):
    # convert integer back to date: 1 -> January 2017
    year, month = divmod(int(x) - 1, 12)
    return datetime.date(year + 2017, month + 1, 1)


class Curve:
    predictions_path = pathlib.Path(__file__).parent / 'predicted-curves'

    @classmethod
    def path_for_key(cls, key):
        path = cls.predictions_path / key
        return path.with_suffix('.npy')

    def __init__(self, key, default_params):
        path = self.path_for_key(key)
        if path.exists():
            self.params = np.load(path)
        else:
            self.params = default_params

    def __repr__(self):
        return f'<{self.__class__.__name__} params=[{", ".join(map(str, self.params))}]>'

    def save_params(self, key):
        self.predictions_path.mkdir(exist_ok=True)
        np.save(self.path_for_key(key), self.params)

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
    # decreases towards 0
    # ∝ 1/x

    def get_value(self, x):
        return self.params[0] / (x + self.params[1])


class Logarithmic(Curve):
    # monotonically increasing
    # ∝ log(x)

    def get_value(self, x):
        return self.params[0] * np.log(self.params[1] * x + self.params[2])


known_curves = {
    'accurate_credits_by_mtp_with_private_estate': {
        'curve': Logarithmic,
        'default_params': np.array([83089128.91457231, 1.6418543562686948e-05, 1.000494203778578], dtype='float64')
    },
    'accurate_credits_by_mtp_without_private_estate': {
        'curve': Logarithmic,
        'default_params': np.array([78402589.76473396, 1.656958576241639e-05, 1.0005337542137802], dtype='float64')
    },
    'extrapolated_credits_by_post_with_private_estate': {
        'curve': Hyperbolic,
        'default_params': np.array([645195.4941409506, 10.977321495885535], dtype='float64'),
    },
    'extrapolated_credits_by_post_without_private_estate': {
        'curve': Hyperbolic,
        'default_params': np.array([639483.4429881874, 10.842087860932255], dtype='float64'),
    },
}


def load_curve(key):
    known_curve = known_curves[key]
    default_params = known_curve['default_params']
    return known_curve['curve'](key, default_params)


def train_curve(key, x, y):
    curve = load_curve(key)
    old_params = curve.params.copy()
    curve.optimise(curve.params, x, y)
    if np.array_equal(old_params, curve.params):
        logger.info('Curve %(key)s already optimised', {'key': key})
    else:
        logger.info('Optimised %(key)s curve: %(curve)s', {'key': key, 'curve': curve})
    curve.save_params(key)
    return curve


def train_digital_takeup(exclude_private_estate=False):
    if exclude_private_estate:
        key_suffix = 'without_private_estate'
    else:
        key_suffix = 'with_private_estate'

    first_of_month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    digital_takeup_per_month = DigitalTakeup.objects.digital_takeup_per_month(
        since=DigitalTakeup.reports_start,
        exclude_private_estate=exclude_private_estate,
    )
    rows = [
        (
            date_to_curve_point(row['date']),
            row['accurate_credits_by_mtp'],
            row['reported_credits_by_post'],
            row['reported_credits_by_mtp'],
        )
        for row in digital_takeup_per_month
        if row['date'] < first_of_month
    ]
    rows = np.array(rows, dtype='int64')
    x = rows[..., 0]

    accurate_credits_by_mtp = rows[..., 1]
    train_curve(f'accurate_credits_by_mtp_{key_suffix}', x, accurate_credits_by_mtp)

    reported_credits_by_post = rows[..., 2]
    reported_credits_by_mtp = rows[..., 3]
    extrapolated_credits_by_post = (
        reported_credits_by_post * accurate_credits_by_mtp / reported_credits_by_mtp
    ).round().astype('int64')
    train_curve(f'extrapolated_credits_by_post_{key_suffix}', x, extrapolated_credits_by_post)
