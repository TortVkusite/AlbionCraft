import unittest
from unittest.mock import Mock
import numpy as np
from scipy.optimize import OptimizeResult,Bounds,LinearConstraint
from app.trip_objective import optimize


class ObjectiveTests(unittest.TestCase):
    def test_timeout_does_not_prove_fractional_optimum(self):
        solver=Mock(side_effect=[
            OptimizeResult(x=np.array([1,0]),status=0,message='cash',mip_dual_bound=-10),
            OptimizeResult(x=np.array([0,1]),status=1,message='timeout',mip_dual_bound=-100)])
        result,_=optimize(solver,[-10,-5],[10,1],Bounds([0,0],[1,1]),
            LinearConstraint([[1,1]],0,1),1,'roi')
        self.assertEqual(result.status,1)
        self.assertEqual(result.x.tolist(),[0,1])
        self.assertIsNone(result.mip_dual_bound)
