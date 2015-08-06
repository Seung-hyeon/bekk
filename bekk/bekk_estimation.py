#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BEKK model class
================

"""
from __future__ import print_function, division

import time

import numpy as np
from scipy.optimize import minimize

from bekk import ParamStandard, ParamSpatial, BEKKResults
from .utils import estimate_h0, likelihood_python, filter_var_python
try:
    from .recursion import filter_var
    from .likelihood import likelihood_gauss
except:
    print('Failed to import cython modules. '
          + 'Temporary hack to compile documentation.')

__all__ = ['BEKK']


class BEKK(object):

    r"""BEKK model.

    .. math::
        u_t = e_t H_t^{1/2},\quad e_t \sim N(0,I),

    with variance matrix evolving accrding to the following recursion:

    .. math::
        H_t = CC^\prime + Au_{t-1}u_{t-1}^\prime A^\prime + BH_{t-1}B^\prime.

    Attributes
    ----------
    innov
        Return innovations
    log_file
        File name to write the results of estimation
    param_start
        Initial values of model parameters
    param_final
        Final values of model parameters
    opt_out
        Optimization results

    Methods
    -------
    estimate
        Estimate parameters of the model

    """

    def __init__(self, innov):
        """Initialize the class.

        Parameters
        ----------
        innov : (nobs, nstocks) array
            Return innovations

        """
        self.innov = innov
        self.log_file = None
        self.param_start = None
        self.param_final = None
        self.method = 'SLSQP'
        self.time_delta = None
        self.opt_out = None
        self.cython = True
        self.hvar = None

    def likelihood(self, theta):
        """Compute the conditional log-likelihood function.

        Parameters
        ----------
        theta : 1dim array
            Dimension depends on the model restriction

        Returns
        -------
        float
            The value of the minus log-likelihood function.
            If some regularity conditions are violated, then it returns
            some obscene number.

        """
        if self.model == 'standard':
            param = ParamStandard.from_theta(theta=theta, target=self.target,
                                             nstocks=self.innov.shape[1],
                                             restriction=self.restriction)
        elif self.model == 'spatial':
            param = ParamSpatial.from_theta(theta=theta, target=self.target,
                                            weights=self.weights)
        else:
            raise NotImplementedError('The model is not implemented!')

        if param.constraint() >= 1 or param.cmat is None:
            return 1e10

        args = [self.hvar, self.innov, param.amat, param.bmat, param.cmat]

        if self.cython:
            filter_var(*args)
            return likelihood_gauss(self.hvar, self.innov)
        else:
            filter_var_python(*args)
            return likelihood_python(self.hvar, self.innov)

    def callback(self, theta):
        """Empty callback function.

        Parameters
        ----------
        theta : 1dim array
            Parameter vector

        """
        pass

    def estimate(self, param_start=None, restriction='scalar', var_target=True,
                 method='SLSQP', cython=True, model='standard', weights=None):
        """Estimate parameters of the BEKK model.

        Updates several attributes of the class.

        Parameters
        ----------
        param_start : BEKKParams instance
            Starting parameters
        model : str
            Specific model to estimate. Must be

                - 'standard'
                - 'spatial'
        restriction : str
            Restriction on parameters. Must be

                - 'full'
                - 'diagonal'
                - 'scalar'
        var_target : bool
            Variance targeting flag. If True, then cmat is not returned.
        weights : (ncat, nstocks, nstocks) array
            Weight matrices for spatial only
        method : str
            Optimization method. See scipy.optimize.minimize
        cython : bool
            Whether to use Cython optimizations (True) or not (False)

        """
        # Update default settings
        nobs, nstocks = self.innov.shape
        target = estimate_h0(self.innov)
        self.restriction = restriction
        self.cython = cython
        self.model = model
        self.weights = weights

        if param_start is not None:
            theta_start = param_start.get_theta(restriction=restriction,
                                                var_target=var_target)
        else:
            param_start = ParamStandard.from_target(target=target)
            theta_start = param_start.get_theta(restriction=restriction,
                                                var_target=var_target)

        if var_target:
            self.target = target
        else:
            self.target = None

        self.hvar = np.zeros((nobs, nstocks, nstocks), dtype=float)
        self.hvar[0] = target.copy()

        # Optimization options
        options = {'disp': False, 'maxiter': int(1e6)}
        # Check for existence of initial guess among arguments.
        # Otherwise, initialize.

        # Start timer for the whole optimization
        time_start = time.time()
        # Run optimization
        opt_out = minimize(self.likelihood, theta_start, method=method,
                                options=options)
        # How much time did it take in minutes?
        time_delta = time.time() - time_start
        # Store optimal parameters in the corresponding class
        if self.model == 'standard':
            param_final = ParamStandard.from_theta(theta=opt_out.x,
                                                     restriction=restriction,
                                                     target=self.target,
                                                     nstocks=nstocks)
        elif self.model == 'spatial':
            param_final = ParamSpatial.from_theta(theta=opt_out.x,
                                                         target=self.target,
                                                         weights=weights)
        else:
            raise NotImplementedError('The model is not implemented!')

        return BEKKResults(param_start=param_start, param_final=param_final,
                           time_delta=time_delta, opt_out=opt_out)