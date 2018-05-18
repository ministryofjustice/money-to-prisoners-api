import unittest

from performance import prediction


class PredictionTestCase(unittest.TestCase):
    def test_curve_fitting(self):
        x = prediction.np.arange(1, 10, dtype='float64')
        y = 1 / (2 * x - 1)
        curve = prediction.Hyperbolic('test', prediction.np.array([1., 1.]))
        curve.optimise(curve.params, x, y)
        self.assertAlmostEqual(curve.params[0], 0.5)
        self.assertAlmostEqual(curve.params[1], -0.5)
